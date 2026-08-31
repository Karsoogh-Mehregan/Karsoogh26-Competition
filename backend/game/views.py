from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsMentor
from core.openapi import OpenApiExample, OpenApiParameter, OpenApiTypes, extend_schema
from game import services
from game.api_exceptions import Conflict, Unprocessable
from game.exceptions import (
    AlreadyGraded,
    AlreadySubmitted,
    GameNotRunning,
    GameServiceError,
    InvalidAnswerPayload,
    MissingFloor,
    NoQuestionAvailable,
    NotTeamMember,
    OccupancyNotActive,
    SubmissionWindowClosed,
)
from game.models import Node, Occupancy, Question, Submission, TeamQuestion
from game.permissions import IsTeamMember
from game.serializers import (
    AssignQuestionSerializer,
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
    summary="Assign a question",
    description="Starts the attempt clock on this holding. Empty body.",
    parameters=_HOLDING_PARAMS,
    request=None,
    responses=HoldingSerializer,
    examples=[OpenApiExample("clock started", value=_HOLDING_ASSIGNED, response_only=True)],
)
class AssignQuestionView(MentorActionView):
    serializer_class = AssignQuestionSerializer

    def post(self, request, team_code: str, node_code: str):
        payload = self.serializer_class(data=request.data)
        payload.is_valid(raise_exception=True)

        team = Team.objects.filter(code=team_code).first()
        if team is None:
            raise NotFound(f"تیم «{team_code}» پیدا نشد.")
        node = Node.objects.select_related("level").filter(code=node_code).first()
        if node is None:
            raise NotFound(f"خانه «{node_code}» پیدا نشد.")

        try:
            with transaction.atomic():
                holding = (
                    Occupancy.objects.active()
                    .select_related("node", "node__level", "team")
                    .filter(team=team, node=node)
                    .first()
                )
                if holding is None:
                    if not Occupancy.objects.active().filter(team=team).exists():
                        raise Conflict("ابتدا یک خانهٔ شروع برای این تیم بگیرید.")
                    if not services.is_adjacent_to_team(team, node):
                        if not services.team_has_expandable_holding(team):
                            raise Conflict(
                                "تا وقتی این خانه نمره نداشته باشد نمی‌توان همسایه را رزرو کرد."
                            )
                        raise Conflict("این خانه همسایهٔ خانه‌های این تیم نیست.")
                    holding = services.enter_node(team, node)
                if holding.question_assigned_at is not None:
                    raise Conflict("سؤال قبلاً به این تیم تخصیص داده شده است.")
                services.assign_question(holding)
                holding.refresh_from_db()
                submission, _created = Submission.objects.get_or_create(
                    occupancy=holding,
                    defaults={
                        "body": "mentor-assigned",
                        "submitted_by": request.user,
                    },
                )
        except GameServiceError as exc:
            _map_service_error(exc)

        data = HoldingSerializer(holding).data
        data["submission_id"] = submission.pk
        return Response(data)


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
