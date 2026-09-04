"""The duel API.

Three reads and two writes:

* `GET  /api/duels/`            — everything the duel page draws, in one call.
* `GET  /api/duels/targets/`    — the table of floors this team may challenge.
* `GET  /api/duels/<pk>/`       — one duel, for a deep link.
* `POST /api/duels/`            — challenge a floor.
* `POST /api/duels/<pk>/resolve/` — the judge names the winner.

The page-shaped read is on purpose. A player's duel page needs their live duel,
their history, whether they may start one and why not — four questions that all
come from the same handful of rows, and four round trips to answer separately.
"""

from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import GameIsRunning
from core.openapi import OpenApiExample, OpenApiParameter, extend_schema
from game.api_exceptions import Conflict, Unprocessable
from game.models import GameSettings
from game.permissions import IsTeamMember
from teams.models import Team

from .exceptions import (
    AlreadyInDuel,
    BuildingNotFull,
    DuelClosed,
    DuelServiceError,
    GameNotRunning,
    InvalidTarget,
    NoRoomAvailable,
    NotAdjacent,
    OnCooldown,
    StakeUnaffordable,
)
from .models import Duel
from .permissions import IsDuelMentor
from .serializers import (
    DuelSerializer,
    DuelTargetSerializer,
    RequestDuelSerializer,
    ResolveDuelSerializer,
)
from .services import (
    challengeable_targets,
    cooldown_until,
    open_duel_for,
    request_duel,
    resolve_duel,
    rooms_available,
)

_DUEL_PK = OpenApiParameter("pk", int, OpenApiParameter.PATH, description="Duel id")

_DUEL_EXAMPLE = {
    "id": 12,
    "attacker": {"code": "alpha", "name": "آلفا", "color": "#ff0000"},
    "attacked": {"code": "beta", "name": "بتا", "color": "#00ff00"},
    "node_code": "L3_12",
    "node_name": "برج شمالی",
    "level": "hard",
    "floor": 2,
    "stake": 1600,
    "status": "open",
    "winner": None,
    "loser": None,
    "mentor": "judge1",
    "room_name": "اتاق ۱",
    "room_link": "https://www.skyroom.online/ch/karsoogh/duel-1",
    "my_role": "attacker",
    "created_at": "2026-09-04T10:00:00Z",
    "resolved_at": None,
}


def _map_service_error(exc: DuelServiceError):
    """Service refusals to HTTP. 409 for "not now", 422 for "not ever"."""
    if isinstance(exc, InvalidTarget):
        raise Unprocessable(str(exc)) from exc
    if isinstance(
        exc,
        (
            AlreadyInDuel,
            BuildingNotFull,
            DuelClosed,
            GameNotRunning,
            NoRoomAvailable,
            NotAdjacent,
            OnCooldown,
            StakeUnaffordable,
        ),
    ):
        raise Conflict(str(exc)) from exc
    raise Unprocessable(str(exc)) from exc


def _serialize(duels, request, *, many=False):
    return DuelSerializer(duels, many=many, context={"request": request}).data


def _blocked_reason(team: Team) -> str:
    """Why this team cannot open a duel right now, or "" if it can.

    Answered here rather than by trying and catching, so the page can grey the
    button out with a sentence next to it instead of waiting for a 409.
    """
    if not GameSettings.load().is_running:
        return "بازی در حال اجرا نیست."
    if open_duel_for(team) is not None:
        return "شما هم‌اکنون یک دوئل باز دارید."
    if cooldown_until(team) is not None:
        return "هنوز در فاصلهٔ استراحت پس از دوئل قبلی هستید."
    if not rooms_available():
        return "در حال حاضر داور آزادی برای دوئل نیست."
    return ""


@extend_schema(
    tags=["duels"],
    summary="The caller's duels",
    description=(
        "Everything the duel page draws. A team gets its live duel, its history and "
        "whether it may start another; a judge additionally gets the duel assigned to "
        "them and the ones they have already called."
    ),
    examples=[
        OpenApiExample(
            "player",
            value={
                "active": _DUEL_EXAMPLE,
                "history": [],
                "judging": None,
                "judged": [],
                "cooldown_until": None,
                "can_request": False,
                "blocked_reason": "شما هم‌اکنون یک دوئل باز دارید.",
            },
            response_only=True,
        )
    ],
)
class DuelListView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DuelSerializer

    def get(self, request):
        user = request.user
        team = user.team if user.team_id else None
        payload = {
            "active": None,
            "history": [],
            "judging": None,
            "judged": [],
            "cooldown_until": None,
            "can_request": False,
            "blocked_reason": "",
        }

        if team is not None:
            active = open_duel_for(team)
            payload["active"] = _serialize(active, request) if active else None
            payload["history"] = _serialize(
                Duel.objects.closed().detailed().for_team(team), request, many=True
            )
            ready_at = cooldown_until(team)
            payload["cooldown_until"] = ready_at.isoformat() if ready_at else None
            reason = _blocked_reason(team)
            payload["blocked_reason"] = reason
            payload["can_request"] = not reason

        if user.has_perm("duels.judge_duel"):
            judging = Duel.objects.open().detailed().filter(mentor=user).first()
            payload["judging"] = _serialize(judging, request) if judging else None
            payload["judged"] = _serialize(
                Duel.objects.closed().detailed().filter(mentor=user), request, many=True
            )

        return Response(payload)

    @extend_schema(
        tags=["duels"],
        summary="Challenge a floor",
        request=RequestDuelSerializer,
        responses=DuelSerializer,
        examples=[
            OpenApiExample("request", value={"occupancy": 41}, request_only=True),
            OpenApiExample("opened", value=_DUEL_EXAMPLE, response_only=True),
        ],
    )
    def post(self, request):
        if not (request.user.team_id and GameSettings.load().is_running):
            raise Conflict("در این وضعیت نمی‌توانید دوئل بزنید.")
        payload = RequestDuelSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            duel = request_duel(request.user.team, payload.validated_data["occupancy"])
        except DuelServiceError as exc:
            _map_service_error(exc)
        return Response(_serialize(duel, request), status=201)


@extend_schema(
    tags=["duels"],
    summary="Floors this team may challenge",
    description=(
        "Every owned floor of every full building adjacent to the team, minus opponents "
        "who are mid-duel or resting. Each row carries the price of challenging it."
    ),
    responses=DuelTargetSerializer(many=True),
    examples=[
        OpenApiExample(
            "targets",
            value=[
                {
                    "occupancy_id": 41,
                    "node_code": "L3_12",
                    "node_name": "برج شمالی",
                    "level": "hard",
                    "floor": 2,
                    "team": {"code": "beta", "name": "بتا", "color": "#00ff00"},
                    "cost": 1600,
                }
            ],
            response_only=True,
        )
    ],
)
class DuelTargetListView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember]
    serializer_class = DuelTargetSerializer

    def get(self, request):
        rows = challengeable_targets(request.user.team)
        return Response(DuelTargetSerializer(rows, many=True).data)


@extend_schema(
    tags=["duels"],
    summary="One duel",
    parameters=[_DUEL_PK],
    responses=DuelSerializer,
    examples=[OpenApiExample("duel", value=_DUEL_EXAMPLE, response_only=True)],
)
class DuelDetailView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DuelSerializer

    def get(self, request, pk: int):
        duel = Duel.objects.detailed().filter(pk=pk).first()
        if duel is None:
            raise NotFound("دوئل پیدا نشد.")
        return Response(_serialize(duel, request))


@extend_schema(
    tags=["duels"],
    summary="Call the winner",
    description=(
        "Closes the duel, moves the floor and settles the stake. Only the judge the "
        "queue assigned to this duel may call it."
    ),
    parameters=[_DUEL_PK],
    request=ResolveDuelSerializer,
    responses=DuelSerializer,
    examples=[
        OpenApiExample("result", value={"winner": "alpha"}, request_only=True),
        OpenApiExample(
            "closed",
            value={**_DUEL_EXAMPLE, "status": "closed", "room_link": None},
            response_only=True,
        ),
    ],
)
class DuelResolveView(APIView):
    permission_classes = [IsAuthenticated, IsDuelMentor, GameIsRunning]
    serializer_class = ResolveDuelSerializer

    def post(self, request, pk: int):
        duel = Duel.objects.detailed().filter(pk=pk).first()
        if duel is None:
            raise NotFound("دوئل پیدا نشد.")
        # Holding judge_duel is not enough: this duel has a judge, and it is the
        # one the rotation named. A superuser can still unstick a duel whose
        # judge is unreachable.
        if duel.mentor_id != request.user.pk and not request.user.is_superuser:
            raise PermissionDenied("داور این دوئل شما نیستید.")

        payload = ResolveDuelSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        winner = Team.objects.filter(code=payload.validated_data["winner"]).first()
        if winner is None:
            raise NotFound("تیم برنده پیدا نشد.")

        try:
            duel = resolve_duel(duel, winner, by=request.user)
        except DuelServiceError as exc:
            _map_service_error(exc)
        return Response(_serialize(duel, request))
