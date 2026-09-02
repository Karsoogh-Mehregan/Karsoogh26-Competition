from datetime import timedelta

from django.conf import settings
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import MENTOR_PERM, IsMentor
from core.openapi import OpenApiExample, OpenApiParameter, extend_schema
from game.api_exceptions import Conflict
from teams.models import Team

from .exceptions import (
    CentipedeError,
    CentipedeNotParticipant,
    CharityBagError,
    NotParticipant,
    OlympicsError,
    TerritoryEventError,
)
from .models import (
    CentipedeDecision,
    CentipedeGame,
    CharityBagEvent,
    CharityBagParticipation,
    OlympicsMatch,
    OlympicsResult,
    TerritoryCell,
    TerritoryGame,
    TerritoryTurn,
)
from .permissions import IsCentipedeParticipant, IsOlympicsParticipant, IsTerritoryParticipant
from .serializers import (
    CentipedeGameSerializer,
    CharityBagEventSerializer,
    CreateCentipedeGameSerializer,
    CreateCharityBagSerializer,
    CreateOlympicsMatchSerializer,
    CreateTerritoryGameSerializer,
    EnterCharityBagSerializer,
    OlympicsMatchSerializer,
    PlayCentipedeActionSerializer,
    PlayTerritoryTurnSerializer,
    RecordOlympicsResultSerializer,
    TerritoryGameStateSerializer,
)
from .services import (
    create_centipede_game,
    create_charity_bag,
    create_olympics_match,
    create_territory_game,
    enter_charity_bag,
    play_centipede_action,
    play_territory_turn,
    record_olympics_result,
    start_olympics_match,
    sync_charity_bag,
    sync_due_charity_bags,
)

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


def charity_bags():
    return CharityBagEvent.objects.prefetch_related(
        Prefetch(
            "participations",
            queryset=CharityBagParticipation.objects.select_related("team"),
        )
    )


def _charity_response(event, request, *, response_status=status.HTTP_200_OK):
    event = charity_bags().get(pk=event.pk)
    serializer = CharityBagEventSerializer(event, context={"request": request})
    return Response(serializer.data, status=response_status)


class CharityBagListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsMentor()]
        return [IsAuthenticated()]

    def get(self, request):
        sync_due_charity_bags()
        serializer = CharityBagEventSerializer(
            charity_bags(),
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    def post(self, request):
        payload = CreateCharityBagSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        starts_at = payload.validated_data.get("starts_at", timezone.now())
        duration = payload.validated_data.get(
            "duration_seconds", settings.CHARITY_BAG_DURATION_SECONDS
        )
        ends_at = payload.validated_data.get("ends_at", starts_at + timedelta(seconds=duration))
        try:
            event = create_charity_bag(starts_at, ends_at)
        except CharityBagError as exc:
            raise Conflict(str(exc)) from exc
        return _charity_response(
            event,
            request,
            response_status=status.HTTP_201_CREATED,
        )


class CharityBagDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        get_object_or_404(CharityBagEvent, pk=pk)
        event = sync_charity_bag(pk)
        return _charity_response(event, request)


class CharityBagParticipationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        if request.user.team_id is None:
            raise PermissionDenied("فقط حساب یک تیم می‌تواند در کیسه خیریه شرکت کند.")
        get_object_or_404(CharityBagEvent, pk=pk)
        payload = EnterCharityBagSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            enter_charity_bag(
                pk,
                request.user.team,
                payload.validated_data["action"],
                payload.validated_data["amount"],
            )
        except CharityBagError as exc:
            raise Conflict(str(exc)) from exc
        event = CharityBagEvent.objects.get(pk=pk)
        return _charity_response(event, request)


class CharityBagResolveView(APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        get_object_or_404(CharityBagEvent, pk=pk)
        event = sync_charity_bag(pk)
        return _charity_response(event, request)


def centipede_games():
    return CentipedeGame.objects.select_related(
        "player_one", "player_two", "active_player", "winner"
    ).prefetch_related(
        Prefetch("decisions", queryset=CentipedeDecision.objects.select_related("actor"))
    )


def _centipede_response(game, *, response_status=status.HTTP_200_OK):
    game = centipede_games().get(pk=game.pk)
    return Response(CentipedeGameSerializer(game).data, status=response_status)


def _map_centipede_error(exc: CentipedeError):
    if isinstance(exc, CentipedeNotParticipant):
        raise PermissionDenied(str(exc)) from exc
    raise Conflict(str(exc)) from exc


class CentipedeGameListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsMentor()]
        return [IsAuthenticated()]

    def get(self, request):
        queryset = centipede_games()
        if not request.user.has_perm(MENTOR_PERM):
            if request.user.team_id is None:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(
                    Q(player_one_id=request.user.team_id) | Q(player_two_id=request.user.team_id)
                )
        return Response(CentipedeGameSerializer(queryset, many=True).data)

    def post(self, request):
        payload = CreateCentipedeGameSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        player_one = get_object_or_404(Team, code=payload.validated_data["player_one"])
        player_two = get_object_or_404(Team, code=payload.validated_data["player_two"])
        try:
            game = create_centipede_game(player_one, player_two)
        except CentipedeError as exc:
            _map_centipede_error(exc)
        return _centipede_response(game, response_status=status.HTTP_201_CREATED)


class CentipedeGameDetailView(APIView):
    permission_classes = [IsAuthenticated, IsCentipedeParticipant]

    def get(self, request, pk: int):
        game = get_object_or_404(centipede_games(), pk=pk)
        self.check_object_permissions(request, game)
        return Response(CentipedeGameSerializer(game).data)


class CentipedeActionView(APIView):
    permission_classes = [IsAuthenticated, IsCentipedeParticipant]

    def post(self, request, pk: int):
        game = get_object_or_404(centipede_games(), pk=pk)
        self.check_object_permissions(request, game)
        if request.user.team_id is None:
            raise PermissionDenied("فقط یکی از دو تیم می‌تواند تصمیم ثبت کند.")
        payload = PlayCentipedeActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            game = play_centipede_action(
                game.pk,
                request.user.team,
                payload.validated_data["action"],
            )
        except CentipedeError as exc:
            _map_centipede_error(exc)
        return _centipede_response(game)


def olympics_matches():
    return OlympicsMatch.objects.select_related(
        "player_one", "player_two", "winner"
    ).prefetch_related(
        Prefetch("results", queryset=OlympicsResult.objects.select_related("recorded_by"))
    )


def _olympics_response(match, *, response_status=status.HTTP_200_OK):
    match = olympics_matches().get(pk=match.pk)
    return Response(OlympicsMatchSerializer(match).data, status=response_status)


class OlympicsMatchListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsMentor()]
        return [IsAuthenticated()]

    def get(self, request):
        queryset = olympics_matches()
        if not request.user.has_perm(MENTOR_PERM):
            if request.user.team_id is None:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(
                    Q(player_one_id=request.user.team_id) | Q(player_two_id=request.user.team_id)
                )
        return Response(OlympicsMatchSerializer(queryset, many=True).data)

    def post(self, request):
        payload = CreateOlympicsMatchSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        player_one = get_object_or_404(Team, code=payload.validated_data["player_one"])
        player_two = get_object_or_404(Team, code=payload.validated_data["player_two"])
        try:
            match = create_olympics_match(
                payload.validated_data["mini_game"],
                player_one,
                player_two,
                payload.validated_data["scoring_zones"],
            )
        except OlympicsError as exc:
            raise Conflict(str(exc)) from exc
        return _olympics_response(match, response_status=status.HTTP_201_CREATED)


class OlympicsMatchDetailView(APIView):
    permission_classes = [IsAuthenticated, IsOlympicsParticipant]

    def get(self, request, pk: int):
        match = get_object_or_404(olympics_matches(), pk=pk)
        self.check_object_permissions(request, match)
        return Response(OlympicsMatchSerializer(match).data)


class OlympicsMatchStartView(APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        get_object_or_404(OlympicsMatch, pk=pk)
        try:
            match = start_olympics_match(pk)
        except OlympicsError as exc:
            raise Conflict(str(exc)) from exc
        return _olympics_response(match)


class OlympicsResultView(APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        get_object_or_404(OlympicsMatch, pk=pk)
        payload = RecordOlympicsResultSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        winner_code = payload.validated_data.get("winner")
        winner = get_object_or_404(Team, code=winner_code) if winner_code else None
        try:
            match = record_olympics_result(
                pk,
                request_id=payload.validated_data["request_id"],
                recorded_by=request.user,
                winner=winner,
                is_tie=payload.validated_data["is_tie"],
                player_one_best_distance=payload.validated_data.get("player_one_best_distance"),
                player_two_best_distance=payload.validated_data.get("player_two_best_distance"),
                player_one_attempts=payload.validated_data["player_one_attempts"],
                player_two_attempts=payload.validated_data["player_two_attempts"],
            )
        except OlympicsError as exc:
            raise Conflict(str(exc)) from exc
        return _olympics_response(match)
