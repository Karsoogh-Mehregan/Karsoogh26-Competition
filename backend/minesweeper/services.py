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
    SettingsDisabled,
    SettingsNotConfigured,
)
from minesweeper.models import (
    DIFFICULTY_BASE_SCORES,
    DIFFICULTY_LAYOUTS,
    MinesweeperAttempt,
    MinesweeperGame,
    MinesweeperSettings,
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


def _generate_layout(width: int, height: int, mine_count: int) -> dict:
    """Build a mine layout with ``mine_count`` mines placed at random."""
    positions = [(row, col) for row in range(height) for col in range(width)]
    mines = set(random.sample(positions, mine_count))
    cells = [
        [
            {
                "mine": (row, col) in mines,
                "adjacent_mines": _adjacent_count(mines, row, col, width=width, height=height),
            }
            for col in range(width)
        ]
        for row in range(height)
    ]
    return {"cells": cells}


def _empty_progress_board(width: int, height: int) -> dict:
    return {
        "cells": [
            [{"revealed": False, "flagged": False} for _ in range(width)] for _ in range(height)
        ]
    }


def _reveal_from(
    layout: dict, progress: dict, row: int, col: int, *, width: int, height: int
) -> None:
    """Reveal ``(row, col)`` on ``progress`` and flood-fill through connected zeros.

    Mines (from ``layout``) and flagged cells are never opened by expansion.
    Numbered safe cells are opened as the boundary and do not propagate.
    """
    progress["cells"][row][col]["revealed"] = True
    start_layout = layout["cells"][row][col]
    if start_layout["mine"] or start_layout["adjacent_mines"] != 0:
        return

    queue = deque([(row, col)])
    while queue:
        cur_row, cur_col = queue.popleft()
        for n_row, n_col in _iter_neighbors(cur_row, cur_col, width=width, height=height):
            neighbor_progress = progress["cells"][n_row][n_col]
            neighbor_layout = layout["cells"][n_row][n_col]
            if (
                neighbor_progress["revealed"]
                or neighbor_progress["flagged"]
                or neighbor_layout["mine"]
            ):
                continue
            neighbor_progress["revealed"] = True
            if neighbor_layout["adjacent_mines"] == 0:
                queue.append((n_row, n_col))


def _locked_in_progress_attempt(attempt_id: int) -> MinesweeperAttempt:
    attempt = (
        MinesweeperAttempt.objects.select_for_update().select_related("game").get(pk=attempt_id)
    )
    if attempt.status != MinesweeperStatus.IN_PROGRESS:
        raise GameFinished("This attempt is already finished.")
    return attempt


def _require_in_bounds(game: MinesweeperGame, row: int, col: int) -> None:
    if not (0 <= row < game.height and 0 <= col < game.width):
        raise InvalidCell(f"Cell ({row}, {col}) is outside the board.")


def _all_safe_cells_revealed(layout: dict, progress: dict) -> bool:
    return all(
        progress_cell["revealed"]
        for layout_row, progress_row in zip(layout["cells"], progress["cells"], strict=True)
        for layout_cell, progress_cell in zip(layout_row, progress_row, strict=True)
        if not layout_cell["mine"]
    )


def _win_score(difficulty: str, started_at: datetime, finished_at: datetime) -> int:
    base = DIFFICULTY_BASE_SCORES[difficulty]
    elapsed_seconds = max(0, math.floor((finished_at - started_at).total_seconds()))
    return base + max(0, base - elapsed_seconds)


def _finish(attempt: MinesweeperAttempt, progress: dict, *, won: bool) -> None:
    now = _now()
    attempt.board = progress
    attempt.finished_at = now
    if won:
        attempt.status = MinesweeperStatus.WON
        attempt.score = _win_score(attempt.game.difficulty, attempt.started_at, now)
    else:
        attempt.status = MinesweeperStatus.LOST
        attempt.score = 0
    attempt.save(update_fields=["board", "status", "score", "finished_at"])


@transaction.atomic
def create_game(node: Node, difficulty: str) -> MinesweeperGame:
    """Create one runtime game with a newly generated mine layout.

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
        node=node,
        difficulty=difficulty,
        width=width,
        height=height,
        mine_count=mine_count,
        board=_generate_layout(width, height, mine_count),
    )


@transaction.atomic
def create_game_from_node(node: Node) -> MinesweeperGame:
    """Read the node's MinesweeperSettings and generate a new runtime game."""
    try:
        settings = MinesweeperSettings.objects.get(node=node)
    except MinesweeperSettings.DoesNotExist:
        raise SettingsNotConfigured("This node has no Minesweeper configuration.") from None
    if not settings.enabled:
        raise SettingsDisabled("Minesweeper is disabled on this node.")
    return create_game(node, settings.difficulty)


@transaction.atomic
def create_attempt(game: MinesweeperGame, team: Team) -> MinesweeperAttempt:
    """Start a new in-progress attempt for ``team`` on ``game``.

    Always inserts. Does not reuse an existing attempt or game.
    """
    return MinesweeperAttempt.objects.create(
        game=game,
        team=team,
        board=_empty_progress_board(game.width, game.height),
    )


def _active_attempt_for(team: Team, node: Node) -> MinesweeperAttempt | None:
    return (
        MinesweeperAttempt.objects.select_related("game")
        .filter(
            team=team,
            game__node_id=node.pk,
            status=MinesweeperStatus.IN_PROGRESS,
        )
        .order_by("-started_at")
        .first()
    )


@transaction.atomic
def start_play(node: Node, team: Team) -> MinesweeperAttempt:
    """Resume this team's in-progress attempt on ``node``, or start a new game.

    Locks the node row so two concurrent starts cannot both insert. A finished
    attempt is left as history; the next visit generates a new board.
    """
    locked_node = Node.objects.select_for_update().get(pk=node.pk)
    active = _active_attempt_for(team, locked_node)
    if active is not None:
        return active
    game = create_game_from_node(locked_node)
    return create_attempt(game, team)


@transaction.atomic
def reveal_cell(attempt_id: int, row: int, col: int) -> MinesweeperAttempt:
    """Reveal one cell on an attempt, flood-filling zeros, then win/loss.

    Locks the attempt row. The game layout is not written. A missing pk raises
    ``MinesweeperAttempt.DoesNotExist``.
    """
    attempt = _locked_in_progress_attempt(attempt_id)
    game = attempt.game
    _require_in_bounds(game, row, col)

    progress_cell = attempt.board["cells"][row][col]
    if progress_cell["revealed"]:
        raise CellAlreadyRevealed("This cell is already revealed.")
    if progress_cell["flagged"]:
        raise CellFlagged("A flagged cell cannot be revealed.")

    clicked_mine = game.board["cells"][row][col]["mine"]
    progress = copy.deepcopy(attempt.board)
    _reveal_from(game.board, progress, row, col, width=game.width, height=game.height)

    if clicked_mine:
        _finish(attempt, progress, won=False)
        return attempt
    if _all_safe_cells_revealed(game.board, progress):
        _finish(attempt, progress, won=True)
        return attempt

    attempt.board = progress
    attempt.save(update_fields=["board"])
    return attempt


@transaction.atomic
def toggle_flag(attempt_id: int, row: int, col: int) -> MinesweeperAttempt:
    """Toggle the flag on one unrevealed cell. Never reveals, never scores."""
    attempt = _locked_in_progress_attempt(attempt_id)
    game = attempt.game
    _require_in_bounds(game, row, col)

    if attempt.board["cells"][row][col]["revealed"]:
        raise CannotFlagRevealed("A revealed cell cannot be flagged.")

    progress = copy.deepcopy(attempt.board)
    target = progress["cells"][row][col]
    target["flagged"] = not target["flagged"]
    attempt.board = progress
    attempt.save(update_fields=["board"])
    return attempt
