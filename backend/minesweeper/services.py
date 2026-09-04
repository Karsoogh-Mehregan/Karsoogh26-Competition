"""Minesweeper domain services. Mutations belong here, not in views."""

import copy
import math
import random
import secrets
from collections import deque
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from game.models import Level, Node
from game.services.events import BOARD_TOLL_CLEARED, BOARD_TOLL_STARTED, publish_on_commit
from game.services.movement import expandable_node_ids, is_reachable
from minesweeper.crossings import has_cleared, is_toll
from minesweeper.exceptions import (
    AlreadyCleared,
    CannotFlagRevealed,
    CellAlreadyRevealed,
    CellFlagged,
    EntryFeeUnaffordable,
    EntryUnauthorized,
    GameFinished,
    InvalidCell,
    InvalidDifficulty,
    NodeUnreachable,
    SettingsDisabled,
    SettingsNotConfigured,
)
from minesweeper.models import (
    DifficultyConfig,
    MinesweeperAttempt,
    MinesweeperGame,
    MinesweeperSettings,
    MinesweeperStatus,
)
from teams.ledger import InsufficientFunds, apply_balance_change
from teams.models import BalanceReason, Team

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


ENTRY_SESSION_KEY = "minesweeper_entry"
ENTRY_TTL = timedelta(seconds=60)

# Which board a gate gets when one is provisioned for it. C34 joins ring 3 to
# ring 4 and C45 joins 4 to 5, so the second gate is the harder sit; both are
# only defaults, and organisers retune them per node in admin or in bulk with
# `manage.py sync_toll_boards --difficulty <key>`.
DEFAULT_TOLL_DIFFICULTIES = {"C34": "easy", "C45": "medium"}
FALLBACK_TOLL_DIFFICULTY = "easy"


def default_toll_difficulty(node_code: str) -> str:
    prefix = node_code.split("_", 1)[0].upper()
    return DEFAULT_TOLL_DIFFICULTIES.get(prefix, FALLBACK_TOLL_DIFFICULTY)


@transaction.atomic
def ensure_toll_boards(*, difficulty: str | None = None) -> dict[str, int]:
    """Give every toll node a Minesweeper board, because a gate with no board is shut.

    A toll takes no question and no occupancy, so its board is the only way
    across it. Provisioning is therefore not optional dressing — it is what
    makes rings 4 and up reachable at all.

    Idempotent. Rows that already exist keep their difficulty and their
    enabled flag unless ``difficulty`` is given, which retunes every gate.
    """
    configured = set(DifficultyConfig.objects.values_list("key", flat=True))
    if difficulty is not None and difficulty not in configured:
        raise InvalidDifficulty(f"Unknown Minesweeper difficulty: {difficulty!r}.")
    if not configured:
        raise InvalidDifficulty("No Minesweeper difficulties are configured.")

    created = updated = unchanged = 0
    for node in Node.objects.filter(level_id=Level.TOLL).order_by("code"):
        wanted = difficulty or default_toll_difficulty(node.code)
        # An organiser may have deleted the difficulty a default names; any
        # configured board beats leaving the gate shut.
        if wanted not in configured:
            wanted = min(configured)
        settings, was_created = MinesweeperSettings.objects.get_or_create(
            node=node, defaults={"difficulty_id": wanted}
        )
        if was_created:
            created += 1
        elif difficulty is not None and settings.difficulty_id != difficulty:
            settings.difficulty_id = difficulty
            settings.save(update_fields=["difficulty", "updated_at"])
            updated += 1
        else:
            unchanged += 1
    return {"created": created, "updated": updated, "unchanged": unchanged}


def _now():
    """Clock seam so tests can pin elapsed time without sleeping."""
    return timezone.now()


def _mark_session_modified(session) -> None:
    if hasattr(session, "modified"):
        session.modified = True


def _require_enabled_settings(node: Node) -> MinesweeperSettings:
    try:
        settings = MinesweeperSettings.objects.select_related("difficulty").get(node=node)
    except MinesweeperSettings.DoesNotExist:
        raise SettingsNotConfigured("This node has no Minesweeper configuration.") from None
    if not settings.enabled:
        raise SettingsDisabled("Minesweeper is disabled on this node.")
    return settings


def require_playable(node: Node, team: Team) -> None:
    """Everything that must hold before this team may open a board on ``node``.

    The gate rules belong to the gates. A board on a toll node *is* the road
    through it, so the team must stand next to it — a holding that already
    expands (a spawn, a graded node, or a gate it has cleared) — and a gate it
    has already beaten is closed to it, because the crossing is permanent and
    paying to replay it would only burn the team's money.

    A board an organiser hangs on any other node stays what it has always been:
    side content, free, playable by anyone with a session.

    None of it applies to a board the team already has open: that one is paid
    for, so going back to it is resuming, not entering, and it stays resumable
    even if the holding the team reached the gate from has since been released.
    """
    _require_enabled_settings(node)
    if not is_toll(node):
        return
    if _active_attempt_for(team, node) is not None:
        return
    if has_cleared(team, node):
        raise AlreadyCleared("This team has already cleared this gate.")
    if not is_reachable(node, expandable_node_ids(team)):
        raise NodeUnreachable("This gate is not adjacent to anything the team holds.")


def _charge_entry(team: Team, node: Node) -> None:
    """Take the gate's entry cost for a newly generated board.

    Charged per board, not per gate: a lost gate may be replayed, and the next
    board costs again. Resuming an unfinished board is free — the team already
    paid for it. Only tolls charge; the cost is the `toll` LevelConfig's, so
    organisers tune it where they tune every other entry cost.
    """
    if not is_toll(node):
        return
    cost = node.level.entry_cost
    if not cost:
        return
    try:
        apply_balance_change(team, -cost, reason=BalanceReason.TOLL, detail=node.code)
    except InsufficientFunds as exc:
        raise EntryFeeUnaffordable("Balance is below this gate's entry cost.") from exc


def issue_entry(session, *, user_id: int, node: Node, team: Team) -> str:
    """Issue a short-lived, one-time map-entry authorization for this session and node.

    Replaces any unused prior intent on the same session. Does not prove the
    player clicked the SVG; it proves that this authenticated session asked to
    enter a gate its team may actually play, so the map reports the refusal on
    the click rather than after the page has opened.
    """
    require_playable(node, team)
    token = secrets.token_urlsafe(32)
    session[ENTRY_SESSION_KEY] = {
        "token": token,
        "node_code": node.code,
        "user_id": user_id,
        "expires_at": (_now() + ENTRY_TTL).isoformat(),
    }
    _mark_session_modified(session)
    return token


def consume_entry(session, *, user_id: int, node: Node, token: str) -> None:
    """Validate and revoke the session's map-entry authorization.

    A matching token is consumed even if the node, user, or expiry check then
    fails, so it cannot be retried on another node.
    """
    intent = session.get(ENTRY_SESSION_KEY)
    stored = intent.get("token") if isinstance(intent, dict) else None
    if not token or not stored:
        raise EntryUnauthorized("No valid Minesweeper entry authorization.")
    try:
        matched = secrets.compare_digest(str(stored), token)
    except (TypeError, ValueError):
        matched = False
    if not matched:
        raise EntryUnauthorized("No valid Minesweeper entry authorization.")

    session.pop(ENTRY_SESSION_KEY, None)
    _mark_session_modified(session)

    if intent.get("user_id") != user_id or intent.get("node_code") != node.code:
        raise EntryUnauthorized("No valid Minesweeper entry authorization.")
    try:
        expires_at = datetime.fromisoformat(intent["expires_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EntryUnauthorized("No valid Minesweeper entry authorization.") from exc
    if expires_at.tzinfo is None:
        expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
    if _now() >= expires_at:
        raise EntryUnauthorized("No valid Minesweeper entry authorization.")


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
        MinesweeperAttempt.objects.select_for_update(of=("self",))
        .select_related("game__node", "game__difficulty")
        .get(pk=attempt_id)
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


def _win_score(base: int, started_at: datetime, finished_at: datetime) -> int:
    """Pay the base twice, less a second for every second taken.

    ``base`` is the board's own snapshot, not today's config: retuning a
    difficulty mid-round must not rescore a board already in play.
    """
    elapsed_seconds = max(0, math.floor((finished_at - started_at).total_seconds()))
    return base + max(0, base - elapsed_seconds)


def _finish(attempt: MinesweeperAttempt, progress: dict, *, won: bool) -> None:
    now = _now()
    attempt.board = progress
    attempt.finished_at = now
    if won:
        attempt.status = MinesweeperStatus.WON
        attempt.score = _win_score(attempt.game.base_score, attempt.started_at, now)
    else:
        attempt.status = MinesweeperStatus.LOST
        attempt.score = 0
    attempt.save(update_fields=["board", "status", "score", "finished_at"])
    if won and is_toll(attempt.game.node):
        # The gate just opened for this team, so the board everyone reads is
        # stale: the frame bumps the snapshot version as well as nudging the SPA.
        publish_on_commit(
            BOARD_TOLL_CLEARED,
            {"team": attempt.team.code, "node": attempt.game.node.code},
        )


@transaction.atomic
def create_game(node: Node, difficulty: DifficultyConfig | str) -> MinesweeperGame:
    """Create one runtime game with a newly generated mine layout.

    ``difficulty`` is a `DifficultyConfig` or its key. Width, height, mine count
    and base score are copied off it here, so the board keeps playing and
    scoring by the numbers it was built with even if the config is retuned.

    ``node`` is stored as association only. This service does not check who
    holds the node and does not change map occupancy.
    """
    if not isinstance(difficulty, DifficultyConfig):
        try:
            difficulty = DifficultyConfig.objects.get(pk=difficulty)
        except DifficultyConfig.DoesNotExist:
            raise InvalidDifficulty(f"Unknown Minesweeper difficulty: {difficulty!r}.") from None

    return MinesweeperGame.objects.create(
        node=node,
        difficulty=difficulty,
        width=difficulty.width,
        height=difficulty.height,
        mine_count=difficulty.mine_count,
        base_score=difficulty.base_score,
        board=_generate_layout(difficulty.width, difficulty.height, difficulty.mine_count),
    )


@transaction.atomic
def create_game_from_node(node: Node) -> MinesweeperGame:
    """Read the node's MinesweeperSettings and generate a new runtime game."""
    settings = _require_enabled_settings(node)
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
        MinesweeperAttempt.objects.select_related("game__node", "game__difficulty")
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
    attempt is left as history; the next visit pays again for a new board.
    """
    # `of=("self",)` so the join for the level config does not lock LevelConfig
    # too; the fee reads that row on every start.
    locked_node = (
        Node.objects.select_for_update(of=("self",)).select_related("level").get(pk=node.pk)
    )
    active = _active_attempt_for(team, locked_node)
    if active is not None:
        return active
    require_playable(locked_node, team)
    game = create_game_from_node(locked_node)
    _charge_entry(team, locked_node)
    attempt = create_attempt(game, team)
    if is_toll(locked_node):
        # The team's balance and its open boards both just changed, and both
        # ride on the row `/api/teams/` caches — so the snapshot needs a new
        # version or the map keeps quoting a toll that has already been paid.
        publish_on_commit(
            BOARD_TOLL_STARTED,
            {"team": team.code, "node": locked_node.code},
        )
    return attempt


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
