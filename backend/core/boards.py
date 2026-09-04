from django.db import models
from rest_framework import status
from rest_framework.exceptions import APIException


class Board(models.TextChoices):
    GIRLS = "girls", "دختران"
    BOYS = "boys", "پسران"


class CrossBoard(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "این دو تیم در دو زمین متفاوت بازی می‌کنند."
    default_code = "cross_board"


def require_same_board(*teams) -> str:
    boards = {team.board for team in teams if team is not None}
    if len(boards) > 1:
        raise CrossBoard()
    return next(iter(boards), None)


def viewing_board(request, *, default: str = Board.GIRLS) -> str:
    if getattr(request.user, "team_id", None) is not None:
        return request.user.team.board
    requested = request.query_params.get("board")
    return requested if requested in Board.values else default


def board_filter(request) -> str | None:
    if getattr(request.user, "team_id", None) is not None:
        return request.user.team.board
    requested = request.query_params.get("board")
    return requested if requested in Board.values else None
