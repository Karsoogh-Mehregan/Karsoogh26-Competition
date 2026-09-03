from rest_framework import status
from rest_framework.exceptions import NotFound
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
    GameFinished,
    InvalidCell,
    InvalidDifficulty,
    MinesweeperServiceError,
    SettingsDisabled,
    SettingsNotConfigured,
)
from minesweeper.models import MinesweeperAttempt, MinesweeperStatus
from minesweeper.serializers import CellActionSerializer, PublicGameSerializer
from minesweeper.services import reveal_cell, start_play, toggle_flag

_NODE_ID = OpenApiParameter("node_id", int, OpenApiParameter.PATH, description="Map node id")
_ATTEMPT_PK = OpenApiParameter(
    "pk", int, OpenApiParameter.PATH, description="Minesweeper attempt id"
)

_PUBLIC_IN_PROGRESS = {
    "game_id": 10,
    "attempt_id": 25,
    "node": 10,
    "difficulty": "hard",
    "width": 30,
    "height": 16,
    "mine_count": 99,
    "status": "in_progress",
    "score": 0,
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
    if isinstance(exc, SettingsDisabled):
        raise Conflict("این بازی مین‌روب فعال نیست.") from exc
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
        attempt = MinesweeperAttempt.objects.select_related("game").get(pk=attempt_id)
    except MinesweeperAttempt.DoesNotExist:
        raise NotFound("بازی پیدا نشد.") from None
    if attempt.team_id != request.user.team_id:
        raise NotFound("بازی پیدا نشد.")
    return attempt


class StartPlayView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = PublicGameSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Start Minesweeper on a node",
        description=(
            "Resumes the caller's in-progress attempt on this node, or generates a new "
            "board from MinesweeperSettings and opens an attempt. One active attempt "
            "per team per node."
        ),
        parameters=[_NODE_ID],
        request=None,
        responses={201: PublicGameSerializer},
        examples=[OpenApiExample("started", value=_PUBLIC_IN_PROGRESS, response_only=True)],
    )
    def post(self, request, node_id: int):
        try:
            node = Node.objects.get(pk=node_id)
        except Node.DoesNotExist:
            raise NotFound("بازی پیدا نشد.") from None
        try:
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
