from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
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
from minesweeper.models import MinesweeperGame
from minesweeper.serializers import (
    CellActionSerializer,
    CreateGameSerializer,
    PublicGameSerializer,
)
from minesweeper.services import create_game, reveal_cell, toggle_flag

_GAME_PK = OpenApiParameter("pk", int, OpenApiParameter.PATH, description="Minesweeper game id")

_PUBLIC_IN_PROGRESS = {
    "id": 1,
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
    if isinstance(exc, MinesweeperGame.DoesNotExist):
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


def _own_game(request, pk: int) -> MinesweeperGame:
    """404 for both missing and other-team games so existence does not leak."""
    game = MinesweeperGame.objects.filter(pk=pk, team_id=request.user.team_id).first()
    if game is None:
        raise NotFound("بازی پیدا نشد.")
    return game


class CreateGameView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = CreateGameSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Start a Minesweeper game",
        description="Creates a game for the caller's own team. Difficulty is required.",
        request=CreateGameSerializer,
        responses={201: PublicGameSerializer},
        examples=[
            OpenApiExample("request", value={"difficulty": "medium"}, request_only=True),
            OpenApiExample("created", value=_PUBLIC_IN_PROGRESS, response_only=True),
        ],
    )
    def post(self, request):
        payload = CreateGameSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            game = create_game(request.user.team, payload.validated_data["difficulty"])
        except MinesweeperServiceError as exc:
            _map_service_error(exc)
        return Response(PublicGameSerializer(game).data, status=status.HTTP_201_CREATED)


class GameDetailView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember]
    serializer_class = PublicGameSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Read a Minesweeper game",
        description="Owning team only. Hidden mines are omitted while the game is in progress.",
        parameters=[_GAME_PK],
        responses=PublicGameSerializer,
        examples=[OpenApiExample("in progress", value=_PUBLIC_IN_PROGRESS, response_only=True)],
    )
    def get(self, request, pk: int):
        game = _own_game(request, pk)
        return Response(PublicGameSerializer(game).data)


class RevealCellView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = CellActionSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Reveal a cell",
        description="Opens one cell and flood-fills zeros. May win or lose the game.",
        parameters=[_GAME_PK],
        request=CellActionSerializer,
        responses=PublicGameSerializer,
        examples=[
            OpenApiExample("request", value={"row": 3, "col": 5}, request_only=True),
            OpenApiExample("opened", value=_PUBLIC_IN_PROGRESS, response_only=True),
        ],
    )
    def post(self, request, pk: int):
        _own_game(request, pk)
        payload = CellActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            game = reveal_cell(pk, payload.validated_data["row"], payload.validated_data["col"])
        except (MinesweeperServiceError, MinesweeperGame.DoesNotExist) as exc:
            _map_service_error(exc)
        return Response(PublicGameSerializer(game).data)


class FlagCellView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = CellActionSerializer

    @extend_schema(
        tags=["minesweeper"],
        summary="Toggle a flag",
        description="Flags or unflags an unrevealed cell. Does not reveal or score.",
        parameters=[_GAME_PK],
        request=CellActionSerializer,
        responses=PublicGameSerializer,
        examples=[
            OpenApiExample("request", value={"row": 3, "col": 5}, request_only=True),
        ],
    )
    def post(self, request, pk: int):
        _own_game(request, pk)
        payload = CellActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            game = toggle_flag(pk, payload.validated_data["row"], payload.validated_data["col"])
        except (MinesweeperServiceError, MinesweeperGame.DoesNotExist) as exc:
            _map_service_error(exc)
        return Response(PublicGameSerializer(game).data)
