from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import MENTOR_PERM, CanViewLeaderboard, GameIsRunning
from core.boards import viewing_board
from core.openapi import OpenApiExample, extend_schema
from game.api_exceptions import Conflict
from game.models import GameSettings, Node
from game.permissions import IsOwnTeam, IsTeamMember
from game.services import (
    claim_spawn,
    release_expired_attempts,
    require_entry_clearance,
    use_fake_document,
    use_gel,
    use_gilari,
)

from . import board_cache
from .leaderboard import ranked_rows, sees_frozen_snapshot
from .models import BalanceEvent, ItemType, Team, TeamItem
from .serializers import (
    BalanceEventSerializer,
    ClaimStartSerializer,
    LeaderboardRowSerializer,
    TeamItemSerializer,
    TeamSerializer,
    UseItemSerializer,
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
                board_cache.snapshot(request, viewing_board(request)),
                is_mentor=user.has_perm(MENTOR_PERM),
                viewer_team_code=user.team.code if user.team_id else None,
            )
        )


@extend_schema(
    tags=["teams"],
    summary="Leaderboard",
    description=(
        "Teams ranked by balance, within one board. A team always sees its own; an "
        "organiser picks with `?board=` and gets the girls' board by default. When "
        "the board is frozen, competing teams get the snapshot taken at the freeze; "
        "organisers keep seeing live ranks."
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
        # One ranking per contest: a team sees only its own board, and ranks
        # restart at 1 on each.
        board = viewing_board(request)
        settings = GameSettings.load()
        if settings.leaderboard_frozen and sees_frozen_snapshot(request.user):
            snap = settings.leaderboard_snapshot or {}
            rows = snap.get(board)
            if isinstance(rows, list):
                return Response(LeaderboardRowSerializer(rows, many=True).data)
        return Response(LeaderboardRowSerializer(ranked_rows(board), many=True).data)


@extend_schema(
    tags=["teams"],
    summary="List the caller's inventory",
    description="Items owned by the logged-in user's team. The team is taken from the session.",
    examples=[
        OpenApiExample(
            "inventory",
            value=[
                {"item_type": "fake_document", "quantity": 1, "display_name": "سند جعلی"},
                {"item_type": "gel", "quantity": 5, "display_name": "گِل"},
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


@extend_schema(
    tags=["teams"],
    summary="Use one inventory item",
    description="The caller team's item. The team is taken from the session.",
    request=UseItemSerializer,
    examples=[
        OpenApiExample(
            "fake_document",
            value={"item_type": "fake_document", "node_code": "h1", "floor": 2},
            request_only=True,
        ),
        OpenApiExample(
            "gilari",
            value={"item_type": "gilari_100"},
            request_only=True,
        ),
        OpenApiExample(
            "used",
            value={"detail": "Item used successfully."},
            response_only=True,
        ),
    ],
)
class UseTeamItemView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember]
    serializer_class = UseItemSerializer

    def post(self, request):
        payload = UseItemSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        team = request.user.team
        item_type = payload.validated_data["item_type"]
        node_code = payload.validated_data["node_code"]
        node = None
        if node_code:
            node = (
                Node.objects.select_related("level")
                .filter(board=team.board, code=node_code)
                .first()
            )
            if node is None:
                raise NotFound(f"خانهٔ «{node_code}» پیدا نشد.")

        if item_type == ItemType.FAKE_DOCUMENT:
            use_fake_document(team, node, payload.validated_data["floor"])
        elif item_type == ItemType.GEL:
            use_gel(team, node)
        else:
            use_gilari(team)

        return Response({"detail": "Item used successfully."})


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
        node = Node.objects.select_related("level").filter(board=team.board, code=node_id).first()
        if node is None:
            raise NotFound(f"خانه «{node_id}» در نقشهٔ سرور نیست.")
        try:
            with transaction.atomic():
                if team.color == color:
                    claim_spawn(team, node)
                elif team.color:
                    raise Conflict("این تیم قبلاً رنگ گرفته است.")
                elif Team.objects.filter(board=team.board, color=color).exists():
                    raise Conflict("این خانهٔ شروع قبلاً گرفته شده است.")
                else:
                    team.color = color
                    team.save(update_fields=["color"])
                    claim_spawn(team, node)
        except IntegrityError as exc:
            raise Conflict("این خانهٔ شروع قبلاً گرفته شده است.") from exc
        data = TeamSerializer(team, context={"request": request}).data
        return Response(data, status=status.HTTP_200_OK)
