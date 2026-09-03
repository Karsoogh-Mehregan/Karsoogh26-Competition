from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import MENTOR_PERM, CanViewLeaderboard, GameIsRunning
from core.openapi import OpenApiExample, extend_schema
from game.api_exceptions import Conflict
from game.models import Node
from game.permissions import IsOwnTeam, IsTeamMember
from game.services import claim_spawn, release_expired_attempts, require_entry_clearance

from . import board_cache
from .models import BalanceEvent, Team, TeamItem
from .serializers import (
    BalanceEventSerializer,
    ClaimStartSerializer,
    LeaderboardRowSerializer,
    TeamItemSerializer,
    TeamSerializer,
)
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
    responses=TeamSerializer(many=True),
)
class TeamListView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamSerializer

    def get(self, request):
        release_expired_attempts()
        user = request.user
        return Response(
            board_cache.mask(
                board_cache.snapshot(request),
                is_mentor=user.has_perm(MENTOR_PERM),
                viewer_team_code=user.team.code if user.team_id else None,
            )
        )


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


@extend_schema(
    tags=["teams"],
    summary="List the caller's inventory",
    description="Items owned by the logged-in user's team. The team is taken from the session.",
    examples=[
        OpenApiExample(
            "inventory",
            value=[
                {"item_type": "fake_document", "quantity": 1, "display_name": "سند جعلی"},
                {"item_type": "gel", "quantity": 5, "display_name": "گل"},
            ],
            response_only=True,
        ),
    ],
    responses=TeamItemSerializer(many=True),
)
class TeamItemListView(APIView):
    """Return the inventory for the caller's own team; no team_code in the URL."""

    permission_classes = [IsAuthenticated, IsTeamMember]
    serializer_class = TeamItemSerializer

    def get(self, request):
        items = TeamItem.objects.filter(team=request.user.team)
        return Response(TeamItemSerializer(items, many=True).data)


class TeamBalanceEventView(APIView):
    """Return the balance-change log for a team (team's own account only)."""

    permission_classes = [IsAuthenticated, IsOwnTeam]

    def get(self, request, team_code: str):
        events = BalanceEvent.objects.filter(team__code=team_code)
        return Response(BalanceEventSerializer(events, many=True).data)


class ClaimStartView(APIView):
    """Claim a start node's color for the team named in the URL.

    Gated on the entry sheet: a team must have cleared it (or the grace window
    must have passed) before it may seat itself on a spawn.
    """

    permission_classes = [IsAuthenticated, IsOwnTeam, GameIsRunning]
    serializer_class = ClaimStartSerializer

    def post(self, request, team_code: str):
        team = Team.objects.filter(code=team_code).first()
        if team is None:
            raise NotFound(f"تیم «{team_code}» پیدا نشد.")
        require_entry_clearance(team)
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
