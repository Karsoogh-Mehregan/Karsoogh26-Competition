from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import GameIsRunning, IsMentor
from core.openapi import OpenApiExample, OpenApiParameter, OpenApiTypes, extend_schema
from game import services
from game.api_exceptions import Conflict, Unprocessable
from game.exceptions import (
    AlreadyGraded,
    AlreadySubmitted,
    EntryAlreadyAnswered,
    EntryAnswerWasCorrect,
    EntryNotAnswered,
    GameNotRunning,
    GameServiceError,
    InvalidAnswerPayload,
    MissingFloor,
    NoEntryQuestions,
    NoEntryRefreshesLeft,
    NoQuestionAvailable,
    NotOnEntrySheet,
    NotTeamMember,
    OccupancyNotActive,
    SubmissionWindowClosed,
)
from game.models import Node, Occupancy, Question, Submission, TeamQuestion
from game.permissions import IsOwnTeam, IsTeamMember
from game.serializers import (
    AssignQuestionSerializer,
    EntryAnswerResultSerializer,
    EntryAnswerSerializer,
    EntrySheetSerializer,
    GradeResultSerializer,
    GradeSerializer,
    GradeSubmissionSerializer,
    HoldingSerializer,
    OccupancyQuestionResponseSerializer,
    QuestionForTeamSerializer,
    ReleaseSerializer,
    SubmissionDetailSerializer,
    SubmissionListSerializer,
    SubmitAnswerSerializer,
    SubmitCreatedSerializer,
    occupancy_for_user,
)
from game.services import grade_submission, submit_answer
from teams.models import Team

_OCCUPANCY_PK = OpenApiParameter("pk", int, OpenApiParameter.PATH, description="Occupancy id")
_SUBMISSION_PK = OpenApiParameter("pk", int, OpenApiParameter.PATH, description="Submission id")
_QUESTION_PK = OpenApiParameter("pk", int, OpenApiParameter.PATH, description="Question id")

_HOLDING_PARAMS = [
    OpenApiParameter("team_code", str, OpenApiParameter.PATH, description="e.g. alpha"),
    OpenApiParameter("node_code", str, OpenApiParameter.PATH, description="e.g. h1"),
]

_HOLDING_ASSIGNED = {
    "team": {"code": "alpha", "name": "Alpha", "balance": 0},
    "node": {"code": "h1", "name": "Hard 1", "level": "hard"},
    "slot": 1,
    "floor": None,
    "grade": None,
    "grade_multiplier": None,
    "points": 0,
    "question_assigned_at": "2026-08-30T10:00:00Z",
    "expires_at": "2026-08-30T10:15:00Z",
    "is_expired": False,
    "entered_at": "2026-08-30T09:55:00Z",
    "released_at": None,
    "release_reason": "",
}
_HOLDING_GRADED = {
    **_HOLDING_ASSIGNED,
    "team": {"code": "alpha", "name": "Alpha", "balance": 200},
    "floor": 1,
    "grade": 90,
    "grade_multiplier": "0.500",
    "points": 200,
}
_HOLDING_RELEASED = {
    **_HOLDING_ASSIGNED,
    "released_at": "2026-08-30T10:12:00Z",
    "release_reason": "expired",
    "is_expired": True,
}

_QUESTION_FOR_TEAM = {
    "code": "q1",
    "title": "Question 1",
    "body": "Body 1",
    "answer_type": "text",
    "attachment_url": None,
    "expires_at": "2026-08-30T10:15:00Z",
    "remaining_seconds": 600,
}
_OCCUPANCY_QUESTION = {
    "occupancy_id": 1,
    "expires_at": "2026-08-30T10:15:00Z",
    "remaining_seconds": 600,
    "question": _QUESTION_FOR_TEAM,
}
_SUBMISSION_ROW = {
    "id": 1,
    "submitted_at": "2026-08-30T10:05:00Z",
    "team_code": "alpha",
    "team_name": "Alpha",
    "node_code": "e1",
    "level": "easy",
    "question_code": "q1",
    "question_title": "Question 1",
    "graded": False,
}
_SUBMISSION_DETAIL = {
    "id": 1,
    "submitted_at": "2026-08-30T10:05:00Z",
    "submitted_by": 3,
    "body": "42",
    "file_url": None,
    "team_code": "alpha",
    "team_name": "Alpha",
    "node_code": "e1",
    "level": "easy",
    "floor": 1,
    "grade": None,
    "points": 0,
    "question": {
        "code": "q1",
        "title": "Question 1",
        "body": "Body 1",
        "answer_type": "text",
        "answer_key": "key1",
        "attachment_url": None,
    },
}


def _map_service_error(exc: GameServiceError):
    if isinstance(exc, NotTeamMember):
        raise PermissionDenied(str(exc)) from exc
    if isinstance(exc, GameNotRunning):
        raise Conflict("بازی در حال اجرا نیست.") from exc
    if isinstance(exc, NoQuestionAvailable):
        raise Conflict("سؤال استفاده نشده‌ای برای این سطح باقی نمانده است.") from exc
    if isinstance(exc, NoEntryQuestions):
        raise Conflict("سؤال ورودی فعالی برای ساختن برگهٔ این تیم وجود ندارد.") from exc
    if isinstance(exc, NotOnEntrySheet):
        raise NotFound("این سؤال روی برگهٔ ورودی این تیم نیست.") from exc
    if isinstance(exc, EntryAlreadyAnswered):
        raise Conflict("به این سؤال قبلاً پاسخ داده‌اید؛ هر سؤال یک فرصت دارد.") from exc
    if isinstance(exc, EntryNotAnswered):
        raise Conflict("ابتدا باید به این سؤال پاسخ دهید.") from exc
    if isinstance(exc, EntryAnswerWasCorrect):
        raise Conflict("پاسخ این سؤال درست بوده و نیازی به تعویض ندارد.") from exc
    if isinstance(exc, NoEntryRefreshesLeft):
        raise Conflict("فرصت تعویض سؤال تمام شده است.") from exc
    if isinstance(
        exc,
        (OccupancyNotActive, SubmissionWindowClosed, AlreadySubmitted),
    ):
        raise Conflict(str(exc)) from exc
    if isinstance(exc, InvalidAnswerPayload):
        raise Unprocessable(str(exc)) from exc
    if isinstance(exc, (AlreadyGraded, MissingFloor)):
        raise Unprocessable(str(exc)) from exc
    raise exc


_ENTRY_ATTEMPT = {
    "position": 1,
    "code": "entry-sum-1-10",
    "title": "جمع یک تا ده",
    "body": "حاصل جمع اعداد ۱ تا ۱۰ چند است؟",
    "answer": None,
    "is_correct": None,
    "answered_at": None,
}
_ENTRY_SHEET = {
    "required_correct": 2,
    "correct_count": 0,
    "answered_count": 0,
    "total_count": 3,
    "qualified": False,
    "grace_over": False,
    "grace_ends_at": "2026-08-30T10:20:00Z",
    "can_claim_start": False,
    "draft_order": None,
    "refreshes_used": 0,
    "refreshes_left": 3,
    "questions": [_ENTRY_ATTEMPT],
}


class EntryViewBase(APIView):
    """The entry sheet belongs to the caller's own team; no team_code in the URL."""

    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]

    def sheet_response(self, team, extra: dict | None = None, serializer=EntrySheetSerializer):
        status_payload = services.entry_status(team)
        return Response(serializer({**status_payload, **(extra or {})}).data)


@extend_schema(
    tags=["entry"],
    summary="Read the entry sheet",
    description=(
        "The caller team's pre-game questions, drawn on first read and stable after that. "
        "Answering enough of them correctly — or waiting out the grace window — is what "
        "unlocks `claim-start/`. Correct answers are never included."
    ),
    responses=EntrySheetSerializer,
    examples=[OpenApiExample("sheet", value=_ENTRY_SHEET, response_only=True)],
)
class EntrySheetView(EntryViewBase):
    serializer_class = EntrySheetSerializer

    def get(self, request):
        team = request.user.team
        try:
            services.assign_entry_sheet(team)
        except GameServiceError as exc:
            _map_service_error(exc)
        return self.sheet_response(team)


@extend_schema(
    tags=["entry"],
    summary="Answer one entry question",
    description=(
        "Integer answer, checked against the database immediately. One shot per question: "
        "a second POST for the same code is a 409."
    ),
    parameters=[
        OpenApiParameter("code", str, OpenApiParameter.PATH, description="e.g. entry-sum-1-10"),
    ],
    request=EntryAnswerSerializer,
    responses=EntryAnswerResultSerializer,
    examples=[
        OpenApiExample("request", value={"answer": 55}, request_only=True),
        OpenApiExample(
            "correct",
            value={
                **_ENTRY_SHEET,
                "is_correct": True,
                "correct_count": 1,
                "answered_count": 1,
            },
            response_only=True,
        ),
    ],
)
class EntryAnswerView(EntryViewBase):
    serializer_class = EntryAnswerSerializer

    def post(self, request, code: str):
        payload = EntryAnswerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        team = request.user.team
        try:
            attempt = services.answer_entry_question(team, code, payload.validated_data["answer"])
        except GameServiceError as exc:
            _map_service_error(exc)

        team.refresh_from_db(fields=["draft_order"])
        return self.sheet_response(
            team,
            extra={"is_correct": attempt.is_correct},
            serializer=EntryAnswerResultSerializer,
        )


@extend_schema(
    tags=["entry"],
    summary="Swap a wrongly-answered entry question",
    description=(
        "Retires a question the team got wrong and seats a fresh one at the same position, "
        "so the team gets another go at qualifying. Capped by "
        "`GameSettings.entry_max_refreshes`; a discarded question is never drawn for that "
        "team again. Only a question that was answered *and* wrong can be swapped."
    ),
    parameters=[
        OpenApiParameter("code", str, OpenApiParameter.PATH, description="e.g. entry-sum-1-10"),
    ],
    request=None,
    responses=EntrySheetSerializer,
    examples=[
        OpenApiExample(
            "swapped",
            value={**_ENTRY_SHEET, "refreshes_used": 1, "refreshes_left": 2},
            response_only=True,
        ),
    ],
)
class EntryRefreshView(EntryViewBase):
    serializer_class = None

    def post(self, request, code: str):
        team = request.user.team
        try:
            services.refresh_entry_question(team, code)
        except GameServiceError as exc:
            _map_service_error(exc)
        return self.sheet_response(team)


@extend_schema(
    tags=["game"],
    summary="Read assigned question",
    description="The question on this occupancy. No answer_key.",
    parameters=[_OCCUPANCY_PK],
    responses=OccupancyQuestionResponseSerializer,
    examples=[OpenApiExample("assigned", value=_OCCUPANCY_QUESTION, response_only=True)],
)
class OccupancyQuestionView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember]

    def get(self, request, pk: int):
        occupancy = occupancy_for_user(pk, request.user)
        if occupancy.team_id != request.user.team_id:
            raise PermissionDenied("Occupancy belongs to another team.")
        if occupancy.question_id is None:
            raise NotFound("No question assigned to this occupancy.")
        if occupancy.released_at is not None:
            raise Conflict("Occupancy is released.")

        serializer = QuestionForTeamSerializer(
            occupancy.question,
            context={"request": request, "expires_at": occupancy.expires_at},
        )
        remaining = serializer.get_remaining_seconds(occupancy.question)
        return Response(
            {
                "occupancy_id": occupancy.pk,
                "expires_at": occupancy.expires_at,
                "remaining_seconds": remaining,
                "question": serializer.data,
            }
        )


@extend_schema(
    tags=["game"],
    summary="Submit an answer",
    description="Body and/or file. Once per occupancy.",
    parameters=[_OCCUPANCY_PK],
    request=SubmitAnswerSerializer,
    responses={201: SubmitCreatedSerializer},
    examples=[
        OpenApiExample("request", value={"body": "42"}, request_only=True),
        OpenApiExample(
            "created",
            value={"id": 1, "submitted_at": "2026-08-30T10:05:00Z"},
            response_only=True,
            status_codes=["201"],
        ),
    ],
)
class OccupancySubmitView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember]

    def post(self, request, pk: int):
        occupancy = occupancy_for_user(pk, request.user)
        payload = SubmitAnswerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            submission = submit_answer(
                occupancy,
                request.user,
                body=payload.validated_data.get("body", ""),
                file=payload.validated_data.get("file"),
            )
        except GameServiceError as exc:
            _map_service_error(exc)

        return Response(
            {
                "id": submission.pk,
                "submitted_at": submission.submitted_at,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["game"],
    summary="List submissions",
    description="Mentor queue. Default is ungraded. Filter with `graded`, `level`, `team`.",
    parameters=[
        OpenApiParameter(
            "graded",
            str,
            OpenApiParameter.QUERY,
            description="true = graded, false (default) = pending",
            enum=["true", "false"],
        ),
        OpenApiParameter("level", str, OpenApiParameter.QUERY, description="e.g. easy"),
        OpenApiParameter("team", str, OpenApiParameter.QUERY, description="e.g. alpha"),
    ],
    examples=[OpenApiExample("pending", value=_SUBMISSION_ROW, response_only=True)],
)
class SubmissionListView(generics.ListAPIView):
    permission_classes = [IsMentor]
    serializer_class = SubmissionListSerializer

    def get_queryset(self):
        qs = Submission.objects.select_related(
            "occupancy__team",
            "occupancy__node__level",
            "occupancy__question",
        ).order_by("-submitted_at")

        graded = self.request.query_params.get("graded")
        if graded == "true":
            qs = qs.filter(occupancy__grade__isnull=False)
        elif graded == "false" or graded is None:
            qs = qs.filter(occupancy__grade__isnull=True)

        level = self.request.query_params.get("level")
        if level:
            qs = qs.filter(occupancy__node__level_id=level)

        team = self.request.query_params.get("team")
        if team:
            qs = qs.filter(occupancy__team__code=team)

        return qs


@extend_schema(
    tags=["game"],
    summary="Submission detail",
    description="Includes answer_key. Mentor only.",
    parameters=[_SUBMISSION_PK],
    examples=[OpenApiExample("detail", value=_SUBMISSION_DETAIL, response_only=True)],
)
class SubmissionDetailView(generics.RetrieveAPIView):
    permission_classes = [IsMentor]
    serializer_class = SubmissionDetailSerializer
    queryset = Submission.objects.select_related(
        "occupancy__team",
        "occupancy__node__level",
        "occupancy__question",
        "submitted_by",
    )


@extend_schema(
    tags=["game"],
    summary="Grade a submission",
    description="Score 0–100. Pays points; grade 0 releases the holding.",
    parameters=[_SUBMISSION_PK],
    request=GradeSubmissionSerializer,
    responses=GradeResultSerializer,
    examples=[
        OpenApiExample("request", value={"grade": 50}, request_only=True),
        OpenApiExample(
            "scored",
            value={
                "occupancy_id": 1,
                "grade": 50,
                "grade_multiplier": "0.500",
                "points": 50,
                "released_at": None,
                "release_reason": "",
            },
            response_only=True,
        ),
    ],
)
class SubmissionGradeView(APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        submission = get_object_or_404(
            Submission.objects.select_related("occupancy__node__level"),
            pk=pk,
        )
        payload = GradeSubmissionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            occupancy = grade_submission(submission, payload.validated_data["grade"])
        except GameServiceError as exc:
            _map_service_error(exc)
        except ValueError as exc:
            raise Unprocessable(str(exc)) from exc

        return Response(
            {
                "occupancy_id": occupancy.pk,
                "grade": occupancy.grade,
                "grade_multiplier": occupancy.grade_multiplier,
                "points": occupancy.points,
                "released_at": occupancy.released_at,
                "release_reason": occupancy.release_reason,
            }
        )


@extend_schema(
    tags=["game"],
    summary="Download submission file",
    description="Owning team or staff.",
    parameters=[_SUBMISSION_PK],
    responses={200: OpenApiTypes.BINARY},
)
class SubmissionMediaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        submission = get_object_or_404(
            Submission.objects.select_related("occupancy__team"),
            pk=pk,
        )
        if not submission.file:
            raise Http404("No file attached.")
        if not request.user.is_staff and submission.occupancy.team_id != request.user.team_id:
            raise PermissionDenied("You cannot access this file.")
        return FileResponse(
            submission.file.open("rb"), as_attachment=True, filename=submission.file.name
        )


@extend_schema(
    tags=["game"],
    summary="Download question attachment",
    description="Staff, or a team that was served this question.",
    parameters=[_QUESTION_PK],
    responses={200: OpenApiTypes.BINARY},
)
class QuestionMediaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        question = get_object_or_404(Question, pk=pk)
        if not question.attachment:
            raise Http404("No attachment.")
        if request.user.is_staff:
            return FileResponse(
                question.attachment.open("rb"),
                as_attachment=True,
                filename=question.attachment.name,
            )
        if request.user.team_id is None:
            raise PermissionDenied("You cannot access this file.")
        served = TeamQuestion.objects.filter(
            team_id=request.user.team_id,
            question=question,
        ).exists()
        if not served:
            raise PermissionDenied("You cannot access this file.")
        return FileResponse(
            question.attachment.open("rb"),
            as_attachment=True,
            filename=question.attachment.name,
        )


class MentorActionView(APIView):
    """One action on the holding named by (team_code, node_code) in the URL.

    The URL identifies the Occupancy outright — a team can hold several nodes at once,
    so naming only the team would be ambiguous.
    """

    permission_classes = [IsMentor]
    serializer_class = None

    def get_holding(self, team_code: str, node_code: str) -> Occupancy:
        holding = (
            Occupancy.objects.active()
            .select_related("node", "node__level", "team")
            .filter(team__code=team_code, node__code=node_code)
            .first()
        )
        if holding is None:
            raise NotFound(f"تیم «{team_code}» واحد فعالی روی خانه «{node_code}» ندارد.")
        return holding

    def perform(self, holding: Occupancy, data: dict) -> Occupancy:
        raise NotImplementedError

    def post(self, request, team_code: str, node_code: str):
        payload = self.serializer_class(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            holding = self.perform(self.get_holding(team_code, node_code), payload.validated_data)
        except GameServiceError as exc:
            _map_service_error(exc)
        return Response(HoldingSerializer(holding).data)


@extend_schema(
    tags=["game"],
    summary="Reserve a node and assign its question",
    description=(
        "Takes a free slot on the node and starts the attempt clock, in one move. "
        "The node must be reachable from a node the team already holds; a team with no "
        "holdings may only take its own start node. Reserving is not owning — the floor "
        "is captured at grading. Charges the level's entry cost. Empty body."
    ),
    parameters=_HOLDING_PARAMS,
    request=None,
    responses=HoldingSerializer,
    examples=[OpenApiExample("clock started", value=_HOLDING_ASSIGNED, response_only=True)],
)
class AssignQuestionView(APIView):
    permission_classes = [IsAuthenticated, IsOwnTeam, GameIsRunning]
    serializer_class = AssignQuestionSerializer

    def post(self, request, team_code: str, node_code: str):
        payload = self.serializer_class(data=request.data)
        payload.is_valid(raise_exception=True)

        team = Team.objects.filter(code=team_code).first()
        if team is None:
            raise NotFound(f"تیم «{team_code}» پیدا نشد.")
        node = Node.objects.select_related("level").filter(code=node_code).first()
        if node is None:
            raise NotFound(f"خانهٔ «{node_code}» پیدا نشد.")

        try:
            holding = services.claim_node(team, node)
        except GameServiceError as exc:
            _map_service_error(exc)

        return Response(HoldingSerializer(holding).data)


@extend_schema(
    tags=["game"],
    summary="Grade the attempt",
    description="Score 0–100. Places the team on a floor and pays points.",
    parameters=_HOLDING_PARAMS,
    request=GradeSerializer,
    responses=HoldingSerializer,
    examples=[
        OpenApiExample("request", value={"grade": 90}, request_only=True),
        OpenApiExample("placed on floor 1", value=_HOLDING_GRADED, response_only=True),
    ],
)
class GradeView(MentorActionView):
    serializer_class = GradeSerializer

    def perform(self, holding, data):
        return services.grade_attempt(holding, data["grade"])


@extend_schema(
    tags=["game"],
    summary="Release the holding",
    description="Frees the slot. `reason` is `expired` or `zero_grade`. Does not change balance.",
    parameters=_HOLDING_PARAMS,
    request=ReleaseSerializer,
    responses=HoldingSerializer,
    examples=[
        OpenApiExample("request", value={"reason": "expired"}, request_only=True),
        OpenApiExample("slot freed", value=_HOLDING_RELEASED, response_only=True),
    ],
)
class ReleaseView(MentorActionView):
    serializer_class = ReleaseSerializer

    def perform(self, holding, data):
        return services.release_attempt(holding, data["reason"])
