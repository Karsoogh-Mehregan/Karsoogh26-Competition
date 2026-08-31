from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsMentor
from core.openapi import OpenApiExample, extend_schema
from game.api_exceptions import Conflict
from game.models import Node
from game.services import enter_node

from .models import Team
from .serializers import ClaimStartSerializer, TeamSerializer
from .start_colors import color_for_start


@extend_schema(
    tags=["teams"],
    summary="List teams",
    description="Every team: code, name, current balance, and the nodes it holds right now.",
    examples=[
        OpenApiExample(
            "team",
            value={
                "code": "alpha",
                "name": "Alpha",
                "balance": 42,
                "holdings": [
                    {
                        "id": 7,
                        "node_code": "n-12",
                        "node_name": "برج شمالی",
                        "level": "easy",
                        "slot": 1,
                        "floor": 2,
                        "grade": 90,
                        "is_spawn": False,
                    }
                ],
            },
            response_only=True,
        ),
    ],
)
class TeamListView(ListAPIView):
    queryset = Team.objects.with_holdings()
    serializer_class = TeamSerializer
    permission_classes = [IsMentor]


class ClaimStartView(APIView):
    """Claim a start node's color for the team named in the URL."""

    permission_classes = [IsMentor]
    serializer_class = ClaimStartSerializer

    def post(self, request, team_code: str):
        team = Team.objects.filter(code=team_code).first()
        if team is None:
            raise NotFound(f"تیم «{team_code}» پیدا نشد.")
        serializer = ClaimStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node_id = serializer.validated_data["node"]
        color = color_for_start(node_id)
        node = Node.objects.select_related("level").filter(code=node_id).first()
        if node is None:
            raise NotFound(f"خانه «{node_id}» در نقشهٔ سرور نیست.")
        try:
            with transaction.atomic():
                if team.color == color:
                    enter_node(team, node, is_spawn=True)
                elif team.color:
                    raise Conflict("این تیم قبلاً رنگ گرفته است.")
                elif Team.objects.filter(color=color).exists():
                    raise Conflict("این خانهٔ شروع قبلاً گرفته شده است.")
                else:
                    team.color = color
                    team.save(update_fields=["color"])
                    enter_node(team, node, is_spawn=True)
        except IntegrityError as exc:
            raise Conflict("این خانهٔ شروع قبلاً گرفته شده است.") from exc
        return Response(TeamSerializer(team).data, status=status.HTTP_200_OK)
