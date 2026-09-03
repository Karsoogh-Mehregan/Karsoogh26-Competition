from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import GameIsRunning
from core.openapi import OpenApiExample, OpenApiParameter, extend_schema
from game.api_exceptions import Conflict, Unprocessable
from game.permissions import IsTeamMember
from minesweeper.exceptions import (
    CannotFlagRevealed,
    CellAlreadyRevealed,
    CellFlagged,
    GameFinished,
    InvalidCell,
    InvalidDifficulty,
    MinesweeperServiceError,
)
from minesweeper.models import MinesweeperAttempt, MinesweeperGame, MinesweeperStatus
from minesweeper.serializers import (
    CellActionSerializer,
    CreateGameSerializer,
    GameDefinitionSerializer,
    PublicGameSerializer,
)
from minesweeper.services import create_game, get_or_create_attempt, reveal_cell, toggle_flag

_GAME_PK = OpenApiParameter("pk", int, OpenApiParameter.PATH, description="Minesweeper game id")

_PUBLIC_IN_PROGRESS = {
    "id": 1,
    "attempt_id": 10,
    "node": 25,
    "difficulty": "easy",
    "width": 9,
    "height": 9,
    "mine_count": 10,
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
    if isinstance(exc, (MinesweeperGame.DoesNotExist, MinesweeperAttempt.DoesNotExist)):
        raise NotFound("بازی پیدا نشد.") from exc
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


def _own_attempt(request, game_id: int, *, require_in_progress: bool) -> MinesweeperAttempt:
    """The caller's attempt for this game. Other teams' rows are invisible (404)."""
    qs = MinesweeperAttempt.objects.select_related("game").filter(
        game_id=game_id,
        team_id=request.user.team_id,
    )
    active = qs.filter(status=MinesweeperStatus.IN_PROGRESS).order_by("-started_at").first()
    if active is not None:
        return active
    if require_in_progress:
        if qs.exists():
            raise GameFinished("This attempt is already finished.")
        raise NotFound("بازی پیدا نشد.")
    latest = qs.order_by("-started_at").first()
    if latest is None:
        raise NotFound("بازی پیدا نشد.")
    return latest


class CreateGameView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = CreateGameSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Create a Minesweeper game definition",
        description=(
            "Staff only. Creates a reusable mine layout on a node. The SPA does not call this; "
            "Django admin is the intended create path."
        ),
        request=CreateGameSerializer,
        responses={201: GameDefinitionSerializer},
        examples=[
            OpenApiExample(
                "request",
                value={"node": 25, "difficulty": "medium"},
                request_only=True,
            ),
            OpenApiExample(
                "created",
                value={
                    "id": 1,
                    "node": 25,
                    "difficulty": "medium",
                    "width": 16,
                    "height": 16,
                    "mine_count": 40,
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request):
        payload = CreateGameSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            game = create_game(
                payload.validated_data["node"],
                payload.validated_data["difficulty"],
            )
        except MinesweeperServiceError as exc:
            _map_service_error(exc)
        return Response(GameDefinitionSerializer(game).data, status=status.HTTP_201_CREATED)


class JoinGameView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = PublicGameSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Join a Minesweeper game",
        description=(
            "Opens or resumes the caller's in-progress attempt on this game. "
            "A second team joining the same game gets its own attempt."
        ),
        parameters=[_GAME_PK],
        request=None,
        responses=PublicGameSerializer,
        examples=[OpenApiExample("joined", value=_PUBLIC_IN_PROGRESS, response_only=True)],
    )
    def post(self, request, pk: int):
        try:
            attempt = get_or_create_attempt(pk, request.user.team)
        except (MinesweeperServiceError, MinesweeperGame.DoesNotExist) as exc:
            _map_service_error(exc)
        return Response(PublicGameSerializer(attempt).data)


class GameDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember]
    serializer_class = PublicGameSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Read the caller's Minesweeper attempt",
        description="Current team's attempt only. Hidden mines are omitted while in progress.",
        parameters=[_GAME_PK],
        responses=PublicGameSerializer,
        examples=[OpenApiExample("in progress", value=_PUBLIC_IN_PROGRESS, response_only=True)],
    )
    def get(self, request, pk: int):
        try:
            attempt = _own_attempt(request, pk, require_in_progress=False)
        except GameFinished as exc:
            _map_service_error(exc)
        return Response(PublicGameSerializer(attempt).data)


class RevealCellView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = CellActionSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Reveal a cell",
        description="Opens one cell on the caller's attempt and flood-fills zeros.",
        parameters=[_GAME_PK],
        request=CellActionSerializer,
        responses=PublicGameSerializer,
        examples=[
            OpenApiExample("request", value={"row": 3, "col": 5}, request_only=True),
            OpenApiExample("opened", value=_PUBLIC_IN_PROGRESS, response_only=True),
        ],
    )
    def post(self, request, pk: int):
        try:
            attempt = _own_attempt(request, pk, require_in_progress=True)
        except GameFinished as exc:
            _map_service_error(exc)
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
        parameters=[_GAME_PK],
        request=CellActionSerializer,
        responses=PublicGameSerializer,
        examples=[
            OpenApiExample("request", value={"row": 3, "col": 5}, request_only=True),
        ],
    )
    def post(self, request, pk: int):
        try:
            attempt = _own_attempt(request, pk, require_in_progress=True)
        except GameFinished as exc:
            _map_service_error(exc)
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
