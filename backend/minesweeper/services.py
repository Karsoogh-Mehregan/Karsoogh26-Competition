"""Minesweeper domain services. Mutations belong here, not in views."""

import copy
import random
from collections import deque

from django.db import transaction

from minesweeper.exceptions import (
    CellAlreadyRevealed,
    CellFlagged,
    GameFinished,
    InvalidCell,
    InvalidDifficulty,
)
from minesweeper.models import DIFFICULTY_LAYOUTS, MinesweeperGame, MinesweeperStatus
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


def _iter_neighbors(row: int, col: int, *, width: int, height: int):
    for d_row, d_col in _NEIGHBOR_OFFSETS:
        n_row = row + d_row
        n_col = col + d_col
        if 0 <= n_row < height and 0 <= n_col < width:
            yield n_row, n_col


def _adjacent_count(
    mines: set[tuple[int, int]], row: int, col: int, *, width: int, height: int
) -> int:
    return sum(
        1 for neighbor in _iter_neighbors(row, col, width=width, height=height) if neighbor in mines
    )


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


def _reveal_from(board: dict, row: int, col: int, *, width: int, height: int) -> None:
    """Reveal ``(row, col)`` and flood-fill through connected zero cells.

    Mines and flagged cells are never opened by expansion. Numbered safe cells
    are opened as the boundary and do not propagate.
    """
    cells = board["cells"]
    start = cells[row][col]
    start["revealed"] = True
    if start["mine"] or start["adjacent_mines"] != 0:
        return

    queue = deque([(row, col)])
    while queue:
        cur_row, cur_col = queue.popleft()
        for n_row, n_col in _iter_neighbors(cur_row, cur_col, width=width, height=height):
            neighbor = cells[n_row][n_col]
            if neighbor["revealed"] or neighbor["flagged"] or neighbor["mine"]:
                continue
            neighbor["revealed"] = True
            if neighbor["adjacent_mines"] == 0:
                queue.append((n_row, n_col))


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


@transaction.atomic
def reveal_cell(game_id: int, row: int, col: int) -> MinesweeperGame:
    """Reveal one cell, flood-filling through connected zeros.

    Locks the game row for the read-modify-write so concurrent reveals cannot
    clobber each other's board. A missing pk raises ``MinesweeperGame.DoesNotExist``
    — the same shape as other services that ``.get()``; views map that to 404.
    Win/loss is not decided here.
    """
    game = MinesweeperGame.objects.select_for_update().get(pk=game_id)

    if game.status != MinesweeperStatus.IN_PROGRESS:
        raise GameFinished("This game is already finished.")

    if not (0 <= row < game.height and 0 <= col < game.width):
        raise InvalidCell(f"Cell ({row}, {col}) is outside the board.")

    cell = game.board["cells"][row][col]
    if cell["revealed"]:
        raise CellAlreadyRevealed("This cell is already revealed.")
    if cell["flagged"]:
        raise CellFlagged("A flagged cell cannot be revealed.")

    board = copy.deepcopy(game.board)
    _reveal_from(board, row, col, width=game.width, height=game.height)
    game.board = board
    game.save(update_fields=["board"])
    return game
