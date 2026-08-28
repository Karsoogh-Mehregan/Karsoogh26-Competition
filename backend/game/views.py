from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from game.api_exceptions import Conflict, Unprocessable
from game.exceptions import (
    AlreadyGraded,
    AlreadySubmitted,
    GameNotRunning,
    GameServiceError,
    InvalidAnswerPayload,
    MissingFloor,
    NotTeamMember,
    OccupancyNotActive,
    SubmissionWindowClosed,
)
from game.models import Occupancy, Question, Submission, TeamQuestion
from game.permissions import IsStaffMentor, IsTeamMember
from game.serializers import (
    GradeSubmissionSerializer,
    QuestionForTeamSerializer,
    SubmissionDetailSerializer,
    SubmissionListSerializer,
    SubmitAnswerSerializer,
    occupancy_for_user,
)
from game.services import grade_submission, submit_answer


def _map_service_error(exc: GameServiceError):
    if isinstance(exc, NotTeamMember):
        raise PermissionDenied(str(exc)) from exc
    if isinstance(exc, (OccupancyNotActive, GameNotRunning, SubmissionWindowClosed, AlreadySubmitted)):
        raise Conflict(str(exc)) from exc
    if isinstance(exc, InvalidAnswerPayload):
        raise Unprocessable(str(exc)) from exc
    if isinstance(exc, (AlreadyGraded, MissingFloor)):
        raise Unprocessable(str(exc)) from exc
    raise exc


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


class SubmissionListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsStaffMentor]
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


class SubmissionDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsStaffMentor]
    serializer_class = SubmissionDetailSerializer
    queryset = Submission.objects.select_related(
        "occupancy__team",
        "occupancy__node__level",
        "occupancy__question",
        "submitted_by",
    )


class SubmissionGradeView(APIView):
    permission_classes = [IsAuthenticated, IsStaffMentor]

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
                "points_awarded": occupancy.points_awarded,
                "released_at": occupancy.released_at,
                "release_reason": occupancy.release_reason,
            }
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
        return FileResponse(submission.file.open("rb"), as_attachment=True, filename=submission.file.name)


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
