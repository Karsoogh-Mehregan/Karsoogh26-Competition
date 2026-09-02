from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanViewLeaderboard, GameIsRunning
from core.openapi import OpenApiExample, extend_schema
from game.api_exceptions import Conflict
from game.models import Node
from game.permissions import IsOwnTeam
from game.services import claim_spawn, release_expired_attempts

from .models import Team
from .serializers import ClaimStartSerializer, LeaderboardRowSerializer, TeamSerializer
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
    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        release_expired_attempts()
        return Team.objects.with_holdings()


@extend_schema(
    tags=["teams"],
    summary="Leaderboard",
    description=(
        "Teams ranked by balance. Visible to mentors always; to teams only once "
        "GameSettings.leaderboard_public is on."
    ),
    examples=[
        OpenApiExample(
            "ranked",
            value=[{"rank": 1, "code": "alpha", "name": "Alpha", "balance": 420}],
            response_only=True,
        ),
    ],
)
class LeaderboardView(APIView):
    permission_classes = [CanViewLeaderboard]

    def get(self, request):
        teams = Team.objects.order_by("-balance", "code")
        rows = [
            {"rank": rank, "code": team.code, "name": team.name, "balance": team.balance}
            for rank, team in enumerate(teams, start=1)
        ]
        return Response(LeaderboardRowSerializer(rows, many=True).data)


class ClaimStartView(APIView):
    """Claim a start node's color for the team named in the URL."""

    permission_classes = [IsAuthenticated, IsOwnTeam, GameIsRunning]
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
                    claim_spawn(team, node)
                elif team.color:
                    raise Conflict("این تیم قبلاً رنگ گرفته است.")
                elif Team.objects.filter(color=color).exists():
                    raise Conflict("این خانهٔ شروع قبلاً گرفته شده است.")
                else:
                    team.color = color
                    team.save(update_fields=["color"])
                    claim_spawn(team, node)
        except IntegrityError as exc:
            raise Conflict("این خانهٔ شروع قبلاً گرفته شده است.") from exc
        data = TeamSerializer(team, context={"request": request}).data
        return Response(data, status=status.HTTP_200_OK)
