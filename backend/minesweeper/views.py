from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import GameIsRunning
from core.openapi import OpenApiExample, OpenApiParameter, extend_schema
from game.api_exceptions import Conflict, Unprocessable
from game.models import Node
from game.permissions import IsTeamMember
from minesweeper.exceptions import (
    CannotFlagRevealed,
    CellAlreadyRevealed,
    CellFlagged,
    EntryFeeUnaffordable,
    EntryUnauthorized,
    GameFinished,
    InvalidCell,
    InvalidDifficulty,
    MinesweeperServiceError,
    NodeUnreachable,
    SettingsDisabled,
    SettingsNotConfigured,
)
from minesweeper.models import MinesweeperAttempt, MinesweeperStatus
from minesweeper.serializers import (
    CellActionSerializer,
    EntryIssuedSerializer,
    PublicGameSerializer,
    StartPlaySerializer,
)
from minesweeper.services import (
    consume_entry,
    issue_entry,
    require_graph_access,
    reveal_cell,
    start_play,
    toggle_flag,
)

_NODE_CODE = OpenApiParameter(
    "node_code", str, OpenApiParameter.PATH, description="Map node code (e.g. C34_0)"
)
_ATTEMPT_PK = OpenApiParameter(
    "pk", int, OpenApiParameter.PATH, description="Minesweeper attempt id"
)

_PUBLIC_IN_PROGRESS = {
    "game_id": 10,
    "attempt_id": 25,
    "node": "C34_0",
    "difficulty": "hard",
    "difficulty_label": "سخت",
    "width": 30,
    "height": 16,
    "mine_count": 99,
    "status": "in_progress",
    "started_at": "2026-09-02T10:00:00Z",
    "finished_at": None,
    "board": {
        "cells": [
            [
                {"revealed": False, "flagged": False},
                {"revealed": True, "flagged": False, "adjacent_mines": 1},
            ]
        ]
    },
}


def _map_service_error(exc: Exception):
    if isinstance(exc, (Node.DoesNotExist, MinesweeperAttempt.DoesNotExist)):
        raise NotFound("بازی پیدا نشد.") from exc
    if isinstance(exc, SettingsNotConfigured):
        raise NotFound("بازی پیدا نشد.") from exc
    if isinstance(exc, EntryUnauthorized):
        raise PermissionDenied("اجازهٔ ورود به این بازی صادر نشده است.") from exc
    if isinstance(exc, NodeUnreachable):
        raise Conflict(str(exc)) from exc
    if isinstance(exc, SettingsDisabled):
        raise Conflict("این بازی مین‌روب فعال نیست.") from exc
    if isinstance(exc, EntryFeeUnaffordable):
        raise Conflict("موجودی تیم برای ورود به این عوارضی کافی نیست.") from exc
    if isinstance(exc, GameFinished):
        raise Conflict("این بازی تمام شده است.") from exc
    if isinstance(exc, InvalidCell):
        raise Unprocessable("این خانه روی صفحه نیست.") from exc
    if isinstance(exc, CellAlreadyRevealed):
        raise Conflict("این خانه قبلاً باز شده است.") from exc
    if isinstance(exc, CellFlagged):
        raise Conflict("خانهٔ پرچم‌دار را نمی‌توان باز کرد.") from exc
    if isinstance(exc, CannotFlagRevealed):
        raise Conflict("خانهٔ بازشده را نمی‌توان پرچم زد.") from exc
    if isinstance(exc, InvalidDifficulty):
        raise Unprocessable("سطح بازی نامعتبر است.") from exc
    if isinstance(exc, MinesweeperServiceError):
        raise Unprocessable(str(exc)) from exc
    raise exc


def _own_attempt(request, attempt_id: int) -> MinesweeperAttempt:
    """The caller's attempt. Other teams' rows are invisible (404)."""
    try:
        attempt = MinesweeperAttempt.objects.select_related("game__node", "game__difficulty").get(
            pk=attempt_id
        )
    except MinesweeperAttempt.DoesNotExist:
        raise NotFound("بازی پیدا نشد.") from None
    if attempt.team_id != request.user.team_id:
        raise NotFound("بازی پیدا نشد.")
    return attempt


def _node_by_code(request, node_code: str) -> Node:
    """The node by that code *on the caller's board*. The other copy is a 404."""
    try:
        return Node.objects.get(board=request.user.team.board, code=node_code)
    except Node.DoesNotExist:
        raise NotFound("بازی پیدا نشد.") from None


class EnterPlayView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = EntryIssuedSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Request Minesweeper map-entry authorization",
        description=(
            "Issues a short-lived, one-time, session-bound authorization for this node. "
            "The SPA must then POST start with that token. The board must be enabled, "
            "and a gate must be reachable from the caller's expandable holdings or a "
            "won Minesweeper toll."
        ),
        parameters=[_NODE_CODE],
        request=None,
        responses={200: EntryIssuedSerializer},
        examples=[
            OpenApiExample(
                "issued",
                value={"entry": "token", "node": "C34_0"},
                response_only=True,
            )
        ],
    )
    def post(self, request, node_code: str):
        node = _node_by_code(request, node_code)
        try:
            token = issue_entry(
                request.session,
                user_id=request.user.pk,
                team=request.user.team,
                node=node,
            )
        except MinesweeperServiceError as exc:
            _map_service_error(exc)
        return Response({"entry": token, "node": node.code})


class StartPlayView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = StartPlaySerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Start or resume Minesweeper on a node",
        description=(
            "Consumes a map-entry token and resumes the caller's in-progress attempt "
            "on this node, or generates a new board and charges the node's entry cost. "
            "One active attempt per team per node."
        ),
        parameters=[_NODE_CODE],
        request=StartPlaySerializer,
        responses={201: PublicGameSerializer},
        examples=[OpenApiExample("started", value=_PUBLIC_IN_PROGRESS, response_only=True)],
    )
    def post(self, request, node_code: str):
        payload = StartPlaySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        node = _node_by_code(request, node_code)
        try:
            require_graph_access(request.user.team, node)
            consume_entry(
                request.session,
                user_id=request.user.pk,
                node=node,
                token=payload.validated_data["entry"],
            )
            attempt = start_play(node, request.user.team)
        except (MinesweeperServiceError, Node.DoesNotExist) as exc:
            _map_service_error(exc)
        return Response(PublicGameSerializer(attempt).data, status=status.HTTP_201_CREATED)


class AttemptDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember]
    serializer_class = PublicGameSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Read the caller's Minesweeper attempt",
        description="Current team's attempt only. Hidden mines are omitted while in progress.",
        parameters=[_ATTEMPT_PK],
        responses=PublicGameSerializer,
        examples=[OpenApiExample("in progress", value=_PUBLIC_IN_PROGRESS, response_only=True)],
    )
    def get(self, request, pk: int):
        return Response(PublicGameSerializer(_own_attempt(request, pk)).data)


class RevealCellView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = CellActionSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Reveal a cell",
        description="Opens one cell on the caller's attempt and flood-fills zeros.",
        parameters=[_ATTEMPT_PK],
        request=CellActionSerializer,
        responses=PublicGameSerializer,
        examples=[
            OpenApiExample("request", value={"row": 3, "col": 5}, request_only=True),
            OpenApiExample("opened", value=_PUBLIC_IN_PROGRESS, response_only=True),
        ],
    )
    def post(self, request, pk: int):
        attempt = _own_attempt(request, pk)
        if attempt.status != MinesweeperStatus.IN_PROGRESS:
            _map_service_error(GameFinished("This attempt is already finished."))
        payload = CellActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            attempt = reveal_cell(
                attempt.pk,
                payload.validated_data["row"],
                payload.validated_data["col"],
            )
        except (MinesweeperServiceError, MinesweeperAttempt.DoesNotExist) as exc:
            _map_service_error(exc)
        return Response(PublicGameSerializer(attempt).data)


class FlagCellView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = CellActionSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Toggle a flag",
        description="Flags or unflags an unrevealed cell on the caller's attempt.",
        parameters=[_ATTEMPT_PK],
        request=CellActionSerializer,
        responses=PublicGameSerializer,
        examples=[
            OpenApiExample("request", value={"row": 3, "col": 5}, request_only=True),
        ],
    )
    def post(self, request, pk: int):
        attempt = _own_attempt(request, pk)
        if attempt.status != MinesweeperStatus.IN_PROGRESS:
            _map_service_error(GameFinished("This attempt is already finished."))
        payload = CellActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            attempt = toggle_flag(
                attempt.pk,
                payload.validated_data["row"],
                payload.validated_data["col"],
            )
        except (MinesweeperServiceError, MinesweeperAttempt.DoesNotExist) as exc:
            _map_service_error(exc)
        return Response(PublicGameSerializer(attempt).data)
