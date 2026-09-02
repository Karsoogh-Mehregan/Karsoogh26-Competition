"""Minesweeper domain services. Mutations belong here, not in views."""

import random

from django.db import transaction

from minesweeper.exceptions import InvalidDifficulty
from minesweeper.models import DIFFICULTY_LAYOUTS, MinesweeperGame
from teams.models import Team

_NEIGHBOR_OFFSETS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


def _adjacent_count(
    mines: set[tuple[int, int]], row: int, col: int, *, width: int, height: int
) -> int:
    count = 0
    for d_row, d_col in _NEIGHBOR_OFFSETS:
        neighbor = (row + d_row, col + d_col)
        n_row, n_col = neighbor
        if 0 <= n_row < height and 0 <= n_col < width and neighbor in mines:
            count += 1
    return count


def _generate_board(width: int, height: int, mine_count: int) -> dict:
    """Build a full server-side grid with ``mine_count`` mines placed at random."""
    positions = [(row, col) for row in range(height) for col in range(width)]
    mines = set(random.sample(positions, mine_count))
    cells = [
        [
            {
                "mine": (row, col) in mines,
                "revealed": False,
                "flagged": False,
                "adjacent_mines": _adjacent_count(mines, row, col, width=width, height=height),
            }
            for col in range(width)
        ]
        for row in range(height)
    ]
    return {"cells": cells}


@transaction.atomic
def create_game(team: Team, difficulty: str) -> MinesweeperGame:
    """Create one in-progress game with a newly generated board.

    ``difficulty`` must be a key of ``DIFFICULTY_LAYOUTS``. Width, height, and
    mine count come from that mapping — they are not caller-supplied.
    """
    try:
        layout = DIFFICULTY_LAYOUTS[difficulty]
    except KeyError:
        raise InvalidDifficulty(f"Unknown Minesweeper difficulty: {difficulty!r}.") from None

    width = layout["width"]
    height = layout["height"]
    mine_count = layout["mine_count"]
    return MinesweeperGame.objects.create(
        team=team,
        difficulty=difficulty,
        width=width,
        height=height,
        mine_count=mine_count,
        board=_generate_board(width, height, mine_count),
    )
