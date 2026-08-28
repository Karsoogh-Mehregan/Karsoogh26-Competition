from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsMentor

from . import services
from .models import Occupancy
from .serializers import (
    AssignQuestionSerializer,
    GradeSerializer,
    HoldingSerializer,
    ReleaseSerializer,
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
        holding = self.perform(self.get_holding(team_code, node_code), payload.validated_data)
        return Response(HoldingSerializer(holding).data)


class AssignQuestionView(MentorActionView):
    serializer_class = AssignQuestionSerializer

    def perform(self, holding, data):
        return services.assign_question(holding)


class GradeView(MentorActionView):
    serializer_class = GradeSerializer

    def perform(self, holding, data):
        return services.grade_attempt(holding, data["grade"])


class ReleaseView(MentorActionView):
    serializer_class = ReleaseSerializer

    def perform(self, holding, data):
        return services.release_attempt(holding, data["reason"])
