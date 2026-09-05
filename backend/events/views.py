from datetime import timedelta

from django.conf import settings
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import MENTOR_PERM, IsMentor
from core.boards import board_filter
from core.openapi import OpenApiExample, OpenApiParameter, extend_schema
from game.api_exceptions import Conflict
from teams.models import Team

from .exceptions import (
    AuctionError,
    CentipedeError,
    CentipedeNotParticipant,
    CharityBagError,
    EventUnavailable,
    MatchmakingError,
    NotParticipant,
    OlympicsError,
    PigError,
    TerritoryEventError,
    WheelError,
)
from .models import (
    AuctionBid,
    AuctionEvent,
    AuctionPair,
    CentipedeDecision,
    CentipedeGame,
    CharityBagEvent,
    CharityBagParticipation,
    EventCode,
    EventConfiguration,
    MatchmakingStatus,
    MatchmakingTicket,
    OlympicsMatch,
    OlympicsResult,
    PigEvent,
    PigGame,
    PigRoll,
    TerritoryCell,
    TerritoryGame,
    TerritoryTurn,
    WheelEvent,
    WheelPrize,
    WheelSpin,
)
from .permissions import IsCentipedeParticipant, IsOlympicsParticipant, IsTerritoryParticipant
from .serializers import (
    AuctionEventSerializer,
    CentipedeGameSerializer,
    CharityBagEventSerializer,
    CreateAuctionEventSerializer,
    CreateCentipedeGameSerializer,
    CreateCharityBagSerializer,
    CreateOlympicsMatchSerializer,
    CreatePigEventSerializer,
    CreateTerritoryGameSerializer,
    CreateWheelEventSerializer,
    EnterCharityBagSerializer,
    EventConfigurationSerializer,
    MatchmakingTicketSerializer,
    OlympicsMatchSerializer,
    PigActionSerializer,
    PigEventSerializer,
    PigGameSerializer,
    PlaceAuctionBidSerializer,
    PlayCentipedeActionSerializer,
    PlayTerritoryTurnSerializer,
    RecordOlympicsResultSerializer,
    SpinWheelSerializer,
    SubmitOlympicsPlayerRunSerializer,
    TerritoryGameStateSerializer,
    WheelEventSerializer,
    WheelSpinSerializer,
)
from .services import (
    cancel_matchmaking,
    create_auction_event,
    create_centipede_game,
    create_charity_bag,
    create_olympics_match,
    create_pig_event,
    create_territory_game,
    create_wheel_event,
    deliver_wheel_prize,
    dismiss_matchmaking,
    ensure_event_configurations,
    enter_charity_bag,
    finish_pig_event,
    join_matchmaking,
    place_auction_bid,
    play_centipede_action,
    play_pig_action,
    play_territory_turn,
    record_olympics_result,
    require_event_enabled,
    settle_auction_event,
    spin_wheel,
    start_olympics_match,
    start_pig_game,
    start_wheel_event,
    stop_wheel_event,
    submit_olympics_player_run,
    sync_charity_bag,
    sync_due_charity_bags,
)


def _event_code_for_request(request, kwargs):
    path = request.path
    if "territory-control" in path:
        return EventCode.TERRITORY_CONTROL
    if "charity-bag" in path:
        return EventCode.CHARITY_BAG
    if "centipede" in path:
        return EventCode.CENTIPEDE
    if "limited-auction" in path:
        return EventCode.LIMITED_AUCTION
    if "prize-wheel" in path:
        return EventCode.PRIZE_WHEEL
    if "/pig/" in path:
        return EventCode.PIG
    if "/olympics/" in path:
        mini_game = request.data.get("mini_game")
        if mini_game == "coin_near_wall":
            return EventCode.OLYMPICS_COIN
        if mini_game == "marble_target":
            return EventCode.OLYMPICS_MARBLE
        match = OlympicsMatch.objects.filter(pk=kwargs.get("pk")).only("mini_game").first()
        if match:
            return (
                EventCode.OLYMPICS_COIN
                if match.mini_game == "coin_near_wall"
                else EventCode.OLYMPICS_MARBLE
            )
    return None


class EventAvailabilityMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            code = _event_code_for_request(request, kwargs)
            if code:
                try:
                    require_event_enabled(code)
                except EventUnavailable as exc:
                    raise PermissionDenied(str(exc)) from exc


def _on_board(manager, board):
    return manager.all() if board is None else manager.filter(board=board)


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


class TerritoryGameListCreateView(EventAvailabilityMixin, APIView):
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
class TerritoryGameDetailView(EventAvailabilityMixin, APIView):
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
class TerritoryTurnView(EventAvailabilityMixin, APIView):
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


def charity_bags(board=None):
    return _on_board(CharityBagEvent.objects, board).prefetch_related(
        Prefetch(
            "participations",
            queryset=CharityBagParticipation.objects.select_related("team"),
        )
    )


def _charity_response(event, request, *, response_status=status.HTTP_200_OK):
    event = charity_bags().get(pk=event.pk)
    serializer = CharityBagEventSerializer(event, context={"request": request})
    return Response(serializer.data, status=response_status)


class CharityBagListCreateView(EventAvailabilityMixin, APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsMentor()]
        return [IsAuthenticated()]

    def get(self, request):
        sync_due_charity_bags()
        serializer = CharityBagEventSerializer(
            charity_bags(board_filter(request)),
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    def post(self, request):
        payload = CreateCharityBagSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        starts_at = payload.validated_data.get("starts_at", timezone.now())
        configuration = require_event_enabled(EventCode.CHARITY_BAG)
        duration = payload.validated_data.get(
            "duration_seconds",
            configuration.duration_seconds or settings.CHARITY_BAG_DURATION_SECONDS,
        )
        ends_at = payload.validated_data.get("ends_at", starts_at + timedelta(seconds=duration))
        minimum_stake = payload.validated_data.get(
            "minimum_stake",
            configuration.settings.get("minimum_stake", settings.CHARITY_BAG_MINIMUM_STAKE),
        )
        freeze_seconds = payload.validated_data.get(
            "freeze_seconds",
            configuration.settings.get("freeze_seconds", settings.CHARITY_BAG_FREEZE_SECONDS),
        )
        try:
            event = create_charity_bag(
                starts_at,
                ends_at,
                board=payload.validated_data["board"],
                minimum_stake=minimum_stake,
                freeze_seconds=freeze_seconds,
            )
        except CharityBagError as exc:
            raise Conflict(str(exc)) from exc
        return _charity_response(
            event,
            request,
            response_status=status.HTTP_201_CREATED,
        )


class CharityBagDetailView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        get_object_or_404(CharityBagEvent, pk=pk)
        event = sync_charity_bag(pk)
        return _charity_response(event, request)


class CharityBagParticipationView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        if request.user.team_id is None:
            raise PermissionDenied("فقط حساب یک تیم می‌تواند در مؤسسه خیریه شرکت کند.")
        get_object_or_404(CharityBagEvent, pk=pk)
        payload = EnterCharityBagSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            enter_charity_bag(
                pk,
                request.user.team,
                payload.validated_data["side"],
                payload.validated_data["amount"],
            )
        except CharityBagError as exc:
            raise Conflict(str(exc)) from exc
        event = CharityBagEvent.objects.get(pk=pk)
        return _charity_response(event, request)


class CharityBagResolveView(EventAvailabilityMixin, APIView):
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


class CentipedeGameListCreateView(EventAvailabilityMixin, APIView):
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


class CentipedeGameDetailView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated, IsCentipedeParticipant]

    def get(self, request, pk: int):
        game = get_object_or_404(centipede_games(), pk=pk)
        self.check_object_permissions(request, game)
        return Response(CentipedeGameSerializer(game).data)


class CentipedeActionView(EventAvailabilityMixin, APIView):
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
                round_number=payload.validated_data["round_number"],
            )
        except CentipedeError as exc:
            _map_centipede_error(exc)
        return _centipede_response(game)


def olympics_matches():
    return OlympicsMatch.objects.select_related(
        "player_one", "player_two", "winner"
    ).prefetch_related(
        Prefetch("results", queryset=OlympicsResult.objects.select_related("recorded_by")),
        "player_runs__team",
    )


def _olympics_response(match, *, response_status=status.HTTP_200_OK):
    match = olympics_matches().get(pk=match.pk)
    return Response(OlympicsMatchSerializer(match).data, status=response_status)


class OlympicsMatchListCreateView(EventAvailabilityMixin, APIView):
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


class OlympicsMatchDetailView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated, IsOlympicsParticipant]

    def get(self, request, pk: int):
        match = get_object_or_404(olympics_matches(), pk=pk)
        self.check_object_permissions(request, match)
        return Response(OlympicsMatchSerializer(match).data)


class OlympicsMatchStartView(EventAvailabilityMixin, APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        get_object_or_404(OlympicsMatch, pk=pk)
        try:
            match = start_olympics_match(pk)
        except OlympicsError as exc:
            raise Conflict(str(exc)) from exc
        return _olympics_response(match)


class OlympicsResultView(EventAvailabilityMixin, APIView):
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


class OlympicsPlayerRunView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        match = get_object_or_404(OlympicsMatch, pk=pk)
        if request.user.team_id not in (match.player_one_id, match.player_two_id):
            raise PermissionDenied("فقط بازیکنان این مسابقه می‌توانند پرتاب کنند.")
        payload = SubmitOlympicsPlayerRunSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            match = submit_olympics_player_run(
                pk,
                request.user.team,
                round_number=payload.validated_data["round_number"],
                attempts=payload.validated_data["attempts"],
                best_distance=payload.validated_data.get("best_distance"),
            )
        except OlympicsError as exc:
            raise Conflict(str(exc)) from exc
        return _olympics_response(match)


def auction_events(board=None):
    return _on_board(AuctionEvent.objects, board).prefetch_related(
        Prefetch(
            "pairs",
            queryset=AuctionPair.objects.select_related(
                "team_one", "team_two", "highest_bidder", "winner"
            ).prefetch_related(
                Prefetch("bids", queryset=AuctionBid.objects.select_related("team"))
            ),
        )
    )


def _auction_response(event, request, *, response_status=status.HTTP_200_OK):
    event = auction_events().get(pk=event.pk)
    return Response(
        AuctionEventSerializer(event, context={"request": request}).data,
        status=response_status,
    )


def _sync_expired_auctions():
    ids = AuctionEvent.objects.filter(status="active", ends_at__lte=timezone.now()).values_list(
        "pk", flat=True
    )
    for event_id in ids:
        settle_auction_event(event_id)


class AuctionEventListCreateView(EventAvailabilityMixin, APIView):
    def get_permissions(self):
        return [IsMentor()] if self.request.method == "POST" else [IsAuthenticated()]

    def get(self, request):
        _sync_expired_auctions()
        return Response(
            AuctionEventSerializer(
                auction_events(board_filter(request)), many=True, context={"request": request}
            ).data
        )

    def post(self, request):
        payload = CreateAuctionEventSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            configuration = require_event_enabled(EventCode.LIMITED_AUCTION)
            event = create_auction_event(
                board=payload.validated_data["board"],
                duration_seconds=payload.validated_data.get("duration_seconds")
                or configuration.duration_seconds
                or 600,
            )
        except AuctionError as exc:
            raise Conflict(str(exc)) from exc
        return _auction_response(event, request, response_status=status.HTTP_201_CREATED)


class AuctionEventDetailView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        event = get_object_or_404(AuctionEvent, pk=pk)
        if event.status == "active" and event.ends_at <= timezone.now():
            event = settle_auction_event(event.pk)
        return _auction_response(event, request)


class AuctionBidView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        if request.user.team_id is None:
            raise PermissionDenied("فقط حساب یک تیم می‌تواند پیشنهاد ثبت کند.")
        get_object_or_404(AuctionPair, pk=pk)
        payload = PlaceAuctionBidSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            pair = place_auction_bid(
                pk,
                request.user.team,
                payload.validated_data["amount"],
                payload.validated_data["request_id"],
            )
        except AuctionError as exc:
            raise Conflict(str(exc)) from exc
        return _auction_response(pair.event, request)


class AuctionResolveView(EventAvailabilityMixin, APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        get_object_or_404(AuctionEvent, pk=pk)
        try:
            event = settle_auction_event(pk)
        except AuctionError as exc:
            raise Conflict(str(exc)) from exc
        return _auction_response(event, request)


def wheel_events(board=None):
    return (
        _on_board(WheelEvent.objects, board)
        .select_related("grand_prize_winner")
        .prefetch_related(
            Prefetch("prizes", queryset=WheelPrize.objects.all()),
            Prefetch("spins", queryset=WheelSpin.objects.select_related("team", "prize")),
        )
    )


def _wheel_response(event, request, *, response_status=status.HTTP_200_OK):
    event = wheel_events().get(pk=event.pk)
    return Response(
        WheelEventSerializer(event, context={"request": request}).data,
        status=response_status,
    )


class WheelEventListCreateView(EventAvailabilityMixin, APIView):
    def get_permissions(self):
        return [IsMentor()] if self.request.method == "POST" else [IsAuthenticated()]

    def get(self, request):
        return Response(
            WheelEventSerializer(
                wheel_events(board_filter(request)), many=True, context={"request": request}
            ).data
        )

    def post(self, request):
        payload = CreateWheelEventSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            event = create_wheel_event(**payload.validated_data)
        except WheelError as exc:
            raise Conflict(str(exc)) from exc
        return _wheel_response(event, request, response_status=status.HTTP_201_CREATED)


class WheelEventDetailView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        return _wheel_response(get_object_or_404(WheelEvent, pk=pk), request)


class WheelStartView(EventAvailabilityMixin, APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        try:
            event = start_wheel_event(pk)
        except (WheelEvent.DoesNotExist, WheelError) as exc:
            raise Conflict(str(exc)) from exc
        return _wheel_response(event, request)


class WheelStopView(EventAvailabilityMixin, APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        try:
            event = stop_wheel_event(pk, cancelled=bool(request.data.get("cancelled", False)))
        except (WheelEvent.DoesNotExist, WheelError) as exc:
            raise Conflict(str(exc)) from exc
        return _wheel_response(event, request)


class WheelSpinView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        if request.user.team_id is None:
            raise PermissionDenied("فقط حساب یک تیم می‌تواند گردونه را بچرخاند.")
        payload = SpinWheelSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            spin = spin_wheel(pk, request.user.team, payload.validated_data["request_id"])
        except (WheelEvent.DoesNotExist, WheelError) as exc:
            raise Conflict(str(exc)) from exc
        return Response(WheelSpinSerializer(spin).data, status=status.HTTP_201_CREATED)


class WheelDeliveryView(EventAvailabilityMixin, APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        try:
            spin = deliver_wheel_prize(pk)
        except (WheelSpin.DoesNotExist, WheelError) as exc:
            raise Conflict(str(exc)) from exc
        return Response(WheelSpinSerializer(spin).data)


def pig_events(board=None):
    return _on_board(PigEvent.objects, board).prefetch_related(
        Prefetch(
            "games",
            queryset=PigGame.objects.select_related("team").prefetch_related(
                Prefetch("rolls", queryset=PigRoll.objects.all())
            ),
        )
    )


def _pig_response(event, request, *, response_status=status.HTTP_200_OK):
    event = pig_events().get(pk=event.pk)
    return Response(
        PigEventSerializer(event, context={"request": request}).data,
        status=response_status,
    )


class PigEventListCreateView(EventAvailabilityMixin, APIView):
    def get_permissions(self):
        return [IsMentor()] if self.request.method == "POST" else [IsAuthenticated()]

    def get(self, request):
        return Response(
            PigEventSerializer(
                pig_events(board_filter(request)), many=True, context={"request": request}
            ).data
        )

    def post(self, request):
        payload = CreatePigEventSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            event = create_pig_event(
                board=payload.validated_data["board"],
                max_pot=payload.validated_data["max_pot"],
            )
        except PigError as exc:
            raise Conflict(str(exc)) from exc
        return _pig_response(event, request, response_status=status.HTTP_201_CREATED)


class PigEventFinishView(EventAvailabilityMixin, APIView):
    permission_classes = [IsMentor]

    def post(self, request, pk: int):
        try:
            event = finish_pig_event(pk)
        except PigEvent.DoesNotExist as exc:
            raise Conflict(str(exc)) from exc
        return _pig_response(event, request)


class PigGameStartView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        if request.user.team_id is None:
            raise PermissionDenied("فقط حساب یک تیم می‌تواند بازی خوک را شروع کند.")
        try:
            game = start_pig_game(pk, request.user.team)
        except (PigEvent.DoesNotExist, PigError) as exc:
            raise Conflict(str(exc)) from exc
        return Response(PigGameSerializer(game).data, status=status.HTTP_201_CREATED)


class PigActionView(EventAvailabilityMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        if request.user.team_id is None:
            raise PermissionDenied("فقط صاحب بازی می‌تواند اقدام ثبت کند.")
        payload = PigActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            game = play_pig_action(
                pk,
                request.user.team,
                payload.validated_data["action"],
                payload.validated_data["request_id"],
            )
        except (PigGame.DoesNotExist, PigError) as exc:
            raise Conflict(str(exc)) from exc
        game = PigGame.objects.select_related("team").prefetch_related("rolls").get(pk=game.pk)
        return Response(PigGameSerializer(game).data)


class EventConfigurationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        configurations = ensure_event_configurations()
        return Response(EventConfigurationSerializer(configurations, many=True).data)


class EventConfigurationUpdateView(APIView):
    permission_classes = [IsMentor]

    def patch(self, request, code: str):
        if code not in EventCode.values:
            return Response({"detail": "رویداد ناشناخته است."}, status=status.HTTP_404_NOT_FOUND)
        configuration, _ = EventConfiguration.objects.get_or_create(code=code)
        serializer = EventConfigurationSerializer(configuration, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MatchmakingListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.team_id is None:
            return Response([])
        tickets = MatchmakingTicket.objects.filter(
            team=request.user.team, dismissed_at__isnull=True
        ).select_related("team", "matched_team")[:30]
        return Response(MatchmakingTicketSerializer(tickets, many=True).data)


class MatchmakingJoinView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code: str):
        if request.user.team_id is None:
            raise PermissionDenied("فقط حساب تیم می‌تواند وارد صف شود.")
        try:
            ticket = join_matchmaking(code, request.user.team)
        except EventUnavailable as exc:
            raise PermissionDenied(str(exc)) from exc
        except MatchmakingError as exc:
            raise Conflict(str(exc)) from exc
        ticket = MatchmakingTicket.objects.select_related("team", "matched_team").get(pk=ticket.pk)
        response_status = (
            status.HTTP_201_CREATED
            if ticket.status == MatchmakingStatus.WAITING
            else status.HTTP_200_OK
        )
        return Response(MatchmakingTicketSerializer(ticket).data, status=response_status)


class MatchmakingCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, code: str):
        if request.user.team_id is None:
            raise PermissionDenied("فقط حساب تیم می‌تواند صف را لغو کند.")
        try:
            ticket = cancel_matchmaking(code, request.user.team)
        except MatchmakingError as exc:
            raise Conflict(str(exc)) from exc
        return Response(MatchmakingTicketSerializer(ticket).data)


class MatchmakingDismissView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        if request.user.team_id is None:
            raise PermissionDenied("فقط حساب تیم می‌تواند از مسابقه خارج شود.")
        try:
            ticket = dismiss_matchmaking(pk, request.user.team)
        except MatchmakingTicket.DoesNotExist as exc:
            raise NotFound("مسابقه‌ای برای این تیم پیدا نشد.") from exc
        except MatchmakingError as exc:
            raise Conflict(str(exc)) from exc
        return Response(MatchmakingTicketSerializer(ticket).data)
