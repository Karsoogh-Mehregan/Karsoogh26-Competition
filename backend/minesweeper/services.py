"""Minesweeper domain services. Mutations belong here, not in views."""

import copy
import math
import random
from collections import deque
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from game.models import Node
from minesweeper.exceptions import (
    CannotFlagRevealed,
    CellAlreadyRevealed,
    CellFlagged,
    GameFinished,
    InvalidCell,
    InvalidDifficulty,
)
from minesweeper.models import (
    DIFFICULTY_BASE_SCORES,
    DIFFICULTY_LAYOUTS,
    MinesweeperGame,
    MinesweeperStatus,
)
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


def _now():
    """Clock seam so tests can pin elapsed time without sleeping."""
    return timezone.now()


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


def _locked_in_progress(game_id: int) -> MinesweeperGame:
    game = MinesweeperGame.objects.select_for_update().get(pk=game_id)
    if game.status != MinesweeperStatus.IN_PROGRESS:
        raise GameFinished("This game is already finished.")
    return game


def _require_in_bounds(game: MinesweeperGame, row: int, col: int) -> None:
    if not (0 <= row < game.height and 0 <= col < game.width):
        raise InvalidCell(f"Cell ({row}, {col}) is outside the board.")


def _all_safe_cells_revealed(board: dict) -> bool:
    return all(cell["revealed"] for row in board["cells"] for cell in row if not cell["mine"])


def _win_score(difficulty: str, started_at: datetime, finished_at: datetime) -> int:
    base = DIFFICULTY_BASE_SCORES[difficulty]
    elapsed_seconds = max(0, math.floor((finished_at - started_at).total_seconds()))
    return base + max(0, base - elapsed_seconds)


def _finish(game: MinesweeperGame, board: dict, *, won: bool) -> None:
    now = _now()
    game.board = board
    game.finished_at = now
    if won:
        game.status = MinesweeperStatus.WON
        game.score = _win_score(game.difficulty, game.started_at, now)
    else:
        game.status = MinesweeperStatus.LOST
        game.score = 0
    game.save(update_fields=["board", "status", "score", "finished_at"])


@transaction.atomic
def create_game(team: Team, node: Node, difficulty: str) -> MinesweeperGame:
    """Create one in-progress game with a newly generated board.

    ``difficulty`` must be a key of ``DIFFICULTY_LAYOUTS``. Width, height, and
    mine count come from that mapping — they are not caller-supplied.

    ``node`` is stored as association only. This service does not check who
    holds the node and does not change map occupancy.
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
        node=node,
        difficulty=difficulty,
        width=width,
        height=height,
        mine_count=mine_count,
        board=_generate_board(width, height, mine_count),
    )


@transaction.atomic
def reveal_cell(game_id: int, row: int, col: int) -> MinesweeperGame:
    """Reveal one cell, flood-filling through connected zeros, then win/loss.

    Locks the game row for the read-modify-write so concurrent reveals cannot
    clobber each other's board. A missing pk raises ``MinesweeperGame.DoesNotExist``
    — the same shape as other services that ``.get()``; views map that to 404.
    """
    game = _locked_in_progress(game_id)
    _require_in_bounds(game, row, col)

    cell = game.board["cells"][row][col]
    if cell["revealed"]:
        raise CellAlreadyRevealed("This cell is already revealed.")
    if cell["flagged"]:
        raise CellFlagged("A flagged cell cannot be revealed.")

    clicked_mine = cell["mine"]
    board = copy.deepcopy(game.board)
    _reveal_from(board, row, col, width=game.width, height=game.height)

    if clicked_mine:
        _finish(game, board, won=False)
        return game
    if _all_safe_cells_revealed(board):
        _finish(game, board, won=True)
        return game

    game.board = board
    game.save(update_fields=["board"])
    return game


@transaction.atomic
def toggle_flag(game_id: int, row: int, col: int) -> MinesweeperGame:
    """Toggle the flag on one unrevealed cell. Never reveals, never scores."""
    game = _locked_in_progress(game_id)
    _require_in_bounds(game, row, col)

    cell = game.board["cells"][row][col]
    if cell["revealed"]:
        raise CannotFlagRevealed("A revealed cell cannot be flagged.")

    board = copy.deepcopy(game.board)
    target = board["cells"][row][col]
    target["flagged"] = not target["flagged"]
    game.board = board
    game.save(update_fields=["board"])
    return game
