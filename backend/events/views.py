from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import MENTOR_PERM, IsMentor
from core.openapi import OpenApiExample, OpenApiParameter, extend_schema
from game.api_exceptions import Conflict
from teams.models import Team

from .exceptions import NotParticipant, TerritoryEventError
from .models import TerritoryCell, TerritoryGame, TerritoryTurn
from .permissions import IsTerritoryParticipant
from .serializers import (
    CreateTerritoryGameSerializer,
    PlayTerritoryTurnSerializer,
    TerritoryGameStateSerializer,
)
from .services import create_territory_game, play_territory_turn

_GAME_PK = OpenApiParameter("pk", int, OpenApiParameter.PATH, description="Territory game id")


def territory_games():
    return TerritoryGame.objects.select_related(
        "player_one", "player_two", "active_player", "winner"
    ).prefetch_related(
        Prefetch("cells", queryset=TerritoryCell.objects.select_related("owner")),
        Prefetch(
            "turns",
            queryset=TerritoryTurn.objects.select_related(
                "acting_player", "previous_owner", "new_owner"
            ),
        ),
    )


def _map_event_error(exc: TerritoryEventError):
    if isinstance(exc, NotParticipant):
        raise PermissionDenied(str(exc)) from exc
    raise Conflict(str(exc)) from exc


class TerritoryGameListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsMentor()]
        return [IsAuthenticated()]

    @extend_schema(
        tags=["events: territory control"],
        summary="List territory-control games",
        description="Mentors see every game; team users only see games they participate in.",
        responses=TerritoryGameStateSerializer(many=True),
    )
    def get(self, request):
        queryset = territory_games()
        if not request.user.has_perm(MENTOR_PERM):
            if request.user.team_id is None:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(
                    Q(player_one_id=request.user.team_id) | Q(player_two_id=request.user.team_id)
                )
        return Response(TerritoryGameStateSerializer(queryset, many=True).data)

    @extend_schema(
        tags=["events: territory control"],
        summary="Create a territory-control game",
        description="Mentor only. Creates the match and its fixed random 5×5 board.",
        request=CreateTerritoryGameSerializer,
        responses={201: TerritoryGameStateSerializer},
        examples=[
            OpenApiExample(
                "create",
                value={"player_one": "alpha", "player_two": "beta"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        payload = CreateTerritoryGameSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        player_one = get_object_or_404(Team, code=payload.validated_data["player_one"])
        player_two = get_object_or_404(Team, code=payload.validated_data["player_two"])
        try:
            game = create_territory_game(player_one, player_two)
        except TerritoryEventError as exc:
            _map_event_error(exc)
        game = territory_games().get(pk=game.pk)
        return Response(TerritoryGameStateSerializer(game).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["events: territory control"],
    summary="Read a territory-control game",
    parameters=[_GAME_PK],
    responses=TerritoryGameStateSerializer,
)
class TerritoryGameDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTerritoryParticipant]

    def get(self, request, pk: int):
        game = get_object_or_404(territory_games(), pk=pk)
        self.check_object_permissions(request, game)
        return Response(TerritoryGameStateSerializer(game).data)


@extend_schema(
    tags=["events: territory control"],
    summary="Play one territory-control turn",
    description=(
        "The authenticated user's team is the acting player. Send only zero-based row and "
        "column coordinates; the backend generates the die result."
    ),
    parameters=[_GAME_PK],
    request=PlayTerritoryTurnSerializer,
    responses=TerritoryGameStateSerializer,
)
class TerritoryTurnView(APIView):
    permission_classes = [IsAuthenticated, IsTerritoryParticipant]

    def post(self, request, pk: int):
        game = get_object_or_404(territory_games(), pk=pk)
        self.check_object_permissions(request, game)
        if request.user.team_id is None:
            raise PermissionDenied("Only a participating team can play a turn.")

        payload = PlayTerritoryTurnSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            play_territory_turn(
                game.pk,
                request.user.team,
                payload.validated_data["row"],
                payload.validated_data["column"],
            )
        except TerritoryEventError as exc:
            _map_event_error(exc)

        game = territory_games().get(pk=game.pk)
        return Response(TerritoryGameStateSerializer(game).data)
