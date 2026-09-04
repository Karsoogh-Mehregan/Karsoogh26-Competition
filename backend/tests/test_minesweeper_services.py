"""Creating a Minesweeper game, attempts, and revealing a cell."""

import copy
import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from game.models import Edge, LevelConfig, Node, Occupancy
from minesweeper.exceptions import (
    CannotFlagRevealed,
    CellAlreadyRevealed,
    CellFlagged,
    EntryUnauthorized,
    GameFinished,
    InvalidCell,
    InvalidDifficulty,
    MinesweeperServiceError,
    NodeUnreachable,
    SettingsDisabled,
    SettingsNotConfigured,
)
from minesweeper.models import (
    DIFFICULTY_BASE_SCORES,
    DIFFICULTY_LAYOUTS,
    MinesweeperAttempt,
    MinesweeperDifficulty,
    MinesweeperGame,
    MinesweeperSettings,
    MinesweeperStatus,
)
from minesweeper.services import (
    consume_entry,
    create_attempt,
    create_game,
    create_game_from_node,
    issue_entry,
    reveal_cell,
    start_play,
    toggle_flag,
)
from teams.models import Team

pytestmark = pytest.mark.django_db

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


@pytest.fixture
def team():
    return Team.objects.create(code="alpha", name="Alpha")


@pytest.fixture
def other_team():
    return Team.objects.create(code="beta", name="Beta")


@pytest.fixture
def node():
    return Node.objects.create(
        code="ms1",
        name="MS 1",
        level=LevelConfig.objects.get(level="easy"),
    )


def _configure(node, difficulty=MinesweeperDifficulty.HARD, *, enabled=True):
    return MinesweeperSettings.objects.create(
        node=node,
        difficulty=difficulty,
        enabled=enabled,
    )


def _undirected(a: Node, b: Node) -> Edge:
    lower, upper = sorted((a, b), key=lambda node: node.pk)
    return Edge.objects.create(a=lower, b=upper, directed=False)


def grant_access(team: Team, node: Node) -> Occupancy:
    """Seat `team` on a spawn home undirected-adjacent to `node`."""
    spawn = LevelConfig.objects.get(level="spawn")
    home = Node.objects.create(
        code=f"ms-home-{team.pk}-{node.pk}",
        name="home",
        level=spawn,
    )
    holding = Occupancy.objects.create(team=team, node=home, slot=1, is_spawn=True)
    _undirected(home, node)
    return holding


def _playing(team, node, difficulty=MinesweeperDifficulty.EASY):
    game = create_game(node, difficulty)
    return create_attempt(game, team)


def _neighbor_mine_count(cells: list[list[dict]], row: int, col: int) -> int:
    """Independent oracle — must not import the production neighbor helper."""
    height = len(cells)
    width = len(cells[0])
    count = 0
    for d_row, d_col in _NEIGHBOR_OFFSETS:
        n_row, n_col = row + d_row, col + d_col
        if 0 <= n_row < height and 0 <= n_col < width and cells[n_row][n_col]["mine"]:
            count += 1
    return count


class TestCreateGame:
    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_creates_a_runtime_board(self, node, difficulty):
        layout = DIFFICULTY_LAYOUTS[difficulty]
        game = create_game(node, difficulty)

        field_names = {field.name for field in MinesweeperGame._meta.get_fields()}
        assert "team" not in field_names
        assert game.node_id == node.pk
        assert game.difficulty == difficulty
        assert game.width == layout["width"]
        assert game.height == layout["height"]
        assert game.mine_count == layout["mine_count"]
        assert game.created_at is not None
        assert MinesweeperAttempt.objects.count() == 0


class TestCreateGameFromNode:
    def test_uses_node_difficulty(self, node):
        _configure(node, MinesweeperDifficulty.HARD)
        game = create_game_from_node(node)
        layout = DIFFICULTY_LAYOUTS[MinesweeperDifficulty.HARD]
        assert game.node_id == node.pk
        assert game.difficulty == MinesweeperDifficulty.HARD
        assert game.width == layout["width"]
        assert game.height == layout["height"]
        assert game.mine_count == layout["mine_count"]
        assert game.board["cells"]

    def test_each_call_creates_a_new_game(self, node):
        _configure(node, MinesweeperDifficulty.EASY)
        first = create_game_from_node(node)
        second = create_game_from_node(node)
        assert first.pk != second.pk
        assert MinesweeperGame.objects.filter(node=node).count() == 2

    def test_missing_settings_are_rejected(self, node):
        with pytest.raises(SettingsNotConfigured) as caught:
            create_game_from_node(node)
        assert isinstance(caught.value, MinesweeperServiceError)
        assert MinesweeperGame.objects.count() == 0

    def test_disabled_settings_are_rejected(self, node):
        _configure(node, MinesweeperDifficulty.MEDIUM, enabled=False)
        with pytest.raises(SettingsDisabled) as caught:
            create_game_from_node(node)
        assert isinstance(caught.value, MinesweeperServiceError)
        assert MinesweeperGame.objects.count() == 0


class TestMapEntry:
    def test_issue_and_consume(self, team, node):
        _configure(node)
        grant_access(team, node)
        session = {}
        token = issue_entry(session, user_id=7, team=team, node=node)
        consume_entry(session, user_id=7, node=node, token=token)

    def test_wrong_node_is_rejected(self, team, node):
        _configure(node)
        grant_access(team, node)
        other = Node.objects.create(
            code="ms-other",
            name="Other",
            level=LevelConfig.objects.get(level="easy"),
        )
        _configure(other)
        grant_access(team, other)
        session = {}
        token = issue_entry(session, user_id=7, team=team, node=node)
        with pytest.raises(EntryUnauthorized):
            consume_entry(session, user_id=7, node=other, token=token)
        with pytest.raises(EntryUnauthorized):
            consume_entry(session, user_id=7, node=node, token=token)

    def test_token_cannot_be_reused(self, team, node):
        _configure(node)
        grant_access(team, node)
        session = {}
        token = issue_entry(session, user_id=7, team=team, node=node)
        consume_entry(session, user_id=7, node=node, token=token)
        with pytest.raises(EntryUnauthorized):
            consume_entry(session, user_id=7, node=node, token=token)

    def test_expired_token_is_rejected(self, team, node, monkeypatch):
        _configure(node)
        grant_access(team, node)
        started = timezone.now()
        monkeypatch.setattr("minesweeper.services._now", lambda: started)
        session = {}
        token = issue_entry(session, user_id=7, team=team, node=node)
        monkeypatch.setattr("minesweeper.services._now", lambda: started + timedelta(seconds=61))
        with pytest.raises(EntryUnauthorized):
            consume_entry(session, user_id=7, node=node, token=token)

    def test_forged_token_is_rejected(self, team, node):
        _configure(node)
        grant_access(team, node)
        session = {}
        issue_entry(session, user_id=7, team=team, node=node)
        with pytest.raises(EntryUnauthorized):
            consume_entry(session, user_id=7, node=node, token="forged")

    def test_wrong_user_is_rejected_and_token_is_consumed(self, team, node):
        _configure(node)
        grant_access(team, node)
        session = {}
        token = issue_entry(session, user_id=7, team=team, node=node)
        with pytest.raises(EntryUnauthorized):
            consume_entry(session, user_id=8, node=node, token=token)
        with pytest.raises(EntryUnauthorized):
            consume_entry(session, user_id=7, node=node, token=token)

    def test_issue_requires_enabled_settings(self, team, node):
        session = {}
        with pytest.raises(SettingsNotConfigured):
            issue_entry(session, user_id=7, team=team, node=node)

    def test_unreachable_node_cannot_issue_a_ticket(self, team, node):
        _configure(node)
        session = {}
        with pytest.raises(NodeUnreachable):
            issue_entry(session, user_id=7, team=team, node=node)


class TestStartPlay:
    @pytest.fixture(autouse=True)
    def _reachable(self, team, other_team, node):
        grant_access(team, node)
        grant_access(other_team, node)

    def test_creates_a_new_game_and_attempt(self, team, node):
        _configure(node, MinesweeperDifficulty.HARD)
        attempt = start_play(node, team)
        assert attempt.team_id == team.pk
        assert attempt.status == MinesweeperStatus.IN_PROGRESS
        assert attempt.game.node_id == node.pk
        assert attempt.game.difficulty == MinesweeperDifficulty.HARD
        assert len(attempt.board["cells"]) == attempt.game.height

    def test_same_team_reentering_resumes_the_active_attempt(self, team, node):
        _configure(node, MinesweeperDifficulty.EASY)
        first = start_play(node, team)
        second = start_play(node, team)
        assert second.pk == first.pk
        assert second.game_id == first.game_id
        assert MinesweeperGame.objects.filter(node=node).count() == 1
        assert MinesweeperAttempt.objects.filter(team=team).count() == 1

    @pytest.mark.parametrize("status", [MinesweeperStatus.WON, MinesweeperStatus.LOST])
    def test_finished_attempt_starts_a_new_game(self, team, node, status):
        _configure(node, MinesweeperDifficulty.EASY)
        first = start_play(node, team)
        _finish(first, status)
        second = start_play(node, team)
        assert second.pk != first.pk
        assert second.game_id != first.game_id
        assert second.status == MinesweeperStatus.IN_PROGRESS
        first.refresh_from_db()
        assert first.status == status
        assert MinesweeperGame.objects.filter(node=node).count() == 2
        assert MinesweeperAttempt.objects.filter(team=team).count() == 2

    def test_different_teams_get_different_games(self, team, other_team, node):
        _configure(node, MinesweeperDifficulty.MEDIUM)
        alpha = start_play(node, team)
        beta = start_play(node, other_team)
        assert alpha.game_id != beta.game_id
        assert alpha.pk != beta.pk
        assert alpha.team_id == team.pk
        assert beta.team_id == other_team.pk
        assert alpha.game.difficulty == MinesweeperDifficulty.MEDIUM
        assert beta.game.difficulty == MinesweeperDifficulty.MEDIUM

    def test_progress_does_not_affect_another_attempt(self, team, other_team, node):
        _configure(node, MinesweeperDifficulty.EASY)
        alpha = start_play(node, team)
        beta = start_play(node, other_team)
        row, col = _find_cell(alpha.game, alpha, mine=False, min_adjacent=1)
        reveal_cell(alpha.pk, row, col)
        alpha.refresh_from_db()
        beta.refresh_from_db()
        assert alpha.board["cells"][row][col]["revealed"] is True
        assert beta.board["cells"][row][col] == {"revealed": False, "flagged": False}
        assert alpha.game_id != beta.game_id


class TestStartPlayGraphGate:
    def test_new_game_requires_reachability(self, team, node):
        _configure(node, MinesweeperDifficulty.EASY)
        with pytest.raises(NodeUnreachable):
            start_play(node, team)
        assert MinesweeperGame.objects.count() == 0

    def test_in_progress_resume_does_not_require_current_reachability(self, team, node):
        _configure(node, MinesweeperDifficulty.EASY)
        attempt = create_attempt(create_game_from_node(node), team)
        resumed = start_play(node, team)
        assert resumed.pk == attempt.pk
        assert MinesweeperGame.objects.filter(node=node).count() == 1


class TestAttempts:
    def test_team_can_create_an_attempt(self, team, node):
        game = create_game(node, MinesweeperDifficulty.EASY)
        attempt = create_attempt(game, team)

        assert attempt.game_id == game.pk
        assert attempt.team_id == team.pk
        assert attempt.status == MinesweeperStatus.IN_PROGRESS
        assert attempt.score == 0
        assert attempt.finished_at is None
        assert len(attempt.board["cells"]) == game.height
        assert all(len(row) == game.width for row in attempt.board["cells"])
        assert all(
            cell == {"revealed": False, "flagged": False}
            for row in attempt.board["cells"]
            for cell in row
        )

    def test_progress_is_isolated_per_attempt(self, team, other_team, node):
        alpha_game = create_game(node, MinesweeperDifficulty.EASY)
        beta_game = create_game(node, MinesweeperDifficulty.EASY)
        alpha = create_attempt(alpha_game, team)
        beta = create_attempt(beta_game, other_team)
        row, col = _find_cell(alpha_game, alpha, mine=False, min_adjacent=1)
        reveal_cell(alpha.pk, row, col)
        alpha.refresh_from_db()
        beta.refresh_from_db()
        assert alpha.board["cells"][row][col]["revealed"] is True
        assert beta.board["cells"][row][col] == {"revealed": False, "flagged": False}


class TestBoardGeneration:
    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_layout_matches_invariants(self, node, difficulty):
        layout = DIFFICULTY_LAYOUTS[difficulty]
        game = create_game(node, difficulty)
        cells = game.board["cells"]

        assert len(cells) == layout["height"]
        assert all(len(row) == layout["width"] for row in cells)

        mines = [cell for row in cells for cell in row if cell["mine"]]
        assert len(mines) == layout["mine_count"]

        for row_index, row in enumerate(cells):
            for col_index, cell in enumerate(row):
                assert set(cell) == {"mine", "adjacent_mines"}
                assert cell["mine"] in (True, False)
                assert cell["adjacent_mines"] == _neighbor_mine_count(cells, row_index, col_index)

    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_layout_is_persisted(self, node, difficulty):
        game = create_game(node, difficulty)
        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.board == game.board
        assert stored.board["cells"]

    def test_adjacent_mines_for_a_known_layout(self, node, monkeypatch):
        """First ten cells (row-major) are mines — a 9×9 easy board."""

        def first_k(population, k):
            return population[:k]

        monkeypatch.setattr("minesweeper.services.random.sample", first_k)
        game = create_game(node, MinesweeperDifficulty.EASY)
        cells = game.board["cells"]

        assert cells[0][0]["mine"] is True
        assert cells[0][8]["mine"] is True
        assert cells[1][0]["mine"] is True
        assert cells[1][1]["mine"] is False
        assert cells[1][1]["adjacent_mines"] == 4
        assert cells[8][8]["mine"] is False
        assert cells[8][8]["adjacent_mines"] == 0


class TestInvalidDifficulty:
    def test_unknown_difficulty_is_rejected(self, node):
        with pytest.raises(InvalidDifficulty) as caught:
            create_game(node, "expert")
        assert isinstance(caught.value, MinesweeperServiceError)
        assert MinesweeperGame.objects.count() == 0


def _find_cell(game, attempt, *, mine: bool, min_adjacent: int | None = None):
    for row_index, row in enumerate(game.board["cells"]):
        for col_index, layout in enumerate(row):
            progress = attempt.board["cells"][row_index][col_index]
            if layout["mine"] is not mine or progress["revealed"] or progress["flagged"]:
                continue
            if min_adjacent is not None and layout["adjacent_mines"] < min_adjacent:
                continue
            return row_index, col_index
    raise AssertionError(f"no unrevealed unflagged cell with mine={mine}")


def _patch_progress(attempt, row, col, **fields):
    board = copy.deepcopy(attempt.board)
    board["cells"][row][col].update(fields)
    attempt.board = board
    attempt.save(update_fields=["board"])
    attempt.refresh_from_db()


def _finish(attempt, status):
    attempt.status = status
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=["status", "finished_at"])
    attempt.refresh_from_db()


SPLIT_MINES = frozenset((row, 4) for row in range(9)) | frozenset({(8, 8)})


def _adjacent_from_mines(mines, row, col, *, width, height) -> int:
    count = 0
    for d_row, d_col in _NEIGHBOR_OFFSETS:
        n_row, n_col = row + d_row, col + d_col
        if 0 <= n_row < height and 0 <= n_col < width and (n_row, n_col) in mines:
            count += 1
    return count


def _make_layout(width, height, mines):
    return {
        "cells": [
            [
                {
                    "mine": (row, col) in mines,
                    "adjacent_mines": _adjacent_from_mines(
                        mines, row, col, width=width, height=height
                    ),
                }
                for col in range(width)
            ]
            for row in range(height)
        ]
    }


def _make_progress(width, height, flags=frozenset()):
    return {
        "cells": [
            [{"revealed": False, "flagged": (row, col) in flags} for col in range(width)]
            for row in range(height)
        ]
    }


def _install_layout(game, mines):
    assert len(mines) == game.mine_count
    game.board = _make_layout(game.width, game.height, mines)
    game.save(update_fields=["board"])
    game.refresh_from_db()


def _install_progress(attempt, flags=frozenset()):
    game = attempt.game
    attempt.board = _make_progress(game.width, game.height, flags)
    attempt.save(update_fields=["board"])
    attempt.refresh_from_db()


def _split_attempt(team, node, flags=frozenset()):
    game = create_game(node, MinesweeperDifficulty.EASY)
    _install_layout(game, SPLIT_MINES)
    attempt = create_attempt(game, team)
    _install_progress(attempt, flags)
    return attempt


def _revealed(board) -> set[tuple[int, int]]:
    return {
        (row, col)
        for row, line in enumerate(board["cells"])
        for col, cell in enumerate(line)
        if cell["revealed"]
    }


def _reveal_all_safe_except(attempt, except_cells: set[tuple[int, int]]):
    layout = attempt.game.board
    progress = copy.deepcopy(attempt.board)
    for row, layout_row in enumerate(layout["cells"]):
        for col, layout_cell in enumerate(layout_row):
            if not layout_cell["mine"] and (row, col) not in except_cells:
                progress["cells"][row][col]["revealed"] = True
    attempt.board = progress
    attempt.save(update_fields=["board"])
    attempt.refresh_from_db()


def _cluster_mines(difficulty) -> frozenset[tuple[int, int]]:
    layout = DIFFICULTY_LAYOUTS[difficulty]
    width, height, count = layout["width"], layout["height"], layout["mine_count"]
    positions = [
        (row, col) for row in range(height - 1, -1, -1) for col in range(width - 1, -1, -1)
    ]
    return frozenset(positions[:count])


def _prepared_attempt(team, node, difficulty):
    game = create_game(node, difficulty)
    _install_layout(game, _cluster_mines(difficulty))
    attempt = create_attempt(game, team)
    _install_progress(attempt)
    return attempt


class TestRevealCell:
    def test_reveals_a_safe_cell_and_persists(self, team, node):
        attempt = _playing(team, node)
        game = attempt.game
        row, col = _find_cell(game, attempt, mine=False, min_adjacent=1)
        original_progress = copy.deepcopy(attempt.board)
        original_layout = copy.deepcopy(game.board)

        updated = reveal_cell(attempt.pk, row, col)
        cell = updated.board["cells"][row][col]

        assert cell["revealed"] is True
        assert cell["flagged"] == original_progress["cells"][row][col]["flagged"]
        assert "mine" not in cell
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.score == 0
        assert updated.finished_at is None

        for r, board_row in enumerate(updated.board["cells"]):
            for c, other in enumerate(board_row):
                if (r, c) == (row, col):
                    continue
                assert other == original_progress["cells"][r][c]

        game.refresh_from_db()
        assert game.board == original_layout
        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.board == updated.board
        assert stored.board["cells"][row][col]["revealed"] is True

    def test_revealing_a_mine_loses_the_attempt(self, team, node):
        attempt = _playing(team, node)
        game = attempt.game
        row, col = _find_cell(game, attempt, mine=True)
        original_layout = copy.deepcopy(game.board)

        updated = reveal_cell(attempt.pk, row, col)
        cell = updated.board["cells"][row][col]

        assert cell["revealed"] is True
        assert game.board["cells"][row][col]["mine"] is True
        assert updated.status == MinesweeperStatus.LOST
        assert updated.score == 0
        assert updated.finished_at is not None
        game.refresh_from_db()
        assert game.board == original_layout

    @pytest.mark.parametrize(
        ("row", "col"),
        [
            (-1, 0),
            (0, -1),
            (9, 0),
            (0, 9),
            (100, 100),
        ],
    )
    def test_invalid_coordinates_leave_the_board_unchanged(self, team, node, row, col):
        attempt = _playing(team, node)
        original = copy.deepcopy(attempt.board)
        original_layout = copy.deepcopy(attempt.game.board)

        with pytest.raises(InvalidCell):
            reveal_cell(attempt.pk, row, col)

        attempt.refresh_from_db()
        attempt.game.refresh_from_db()
        assert attempt.board == original
        assert attempt.game.board == original_layout

    def test_already_revealed_cell_is_rejected(self, team, node):
        attempt = _playing(team, node)
        game = attempt.game
        row, col = _find_cell(game, attempt, mine=False)
        reveal_cell(attempt.pk, row, col)
        original = copy.deepcopy(MinesweeperAttempt.objects.get(pk=attempt.pk).board)

        with pytest.raises(CellAlreadyRevealed):
            reveal_cell(attempt.pk, row, col)

        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.board == original

    def test_flagged_cell_is_not_revealed(self, team, node):
        attempt = _playing(team, node)
        game = attempt.game
        row, col = _find_cell(game, attempt, mine=False)
        _patch_progress(attempt, row, col, flagged=True)
        original = copy.deepcopy(attempt.board)

        with pytest.raises(CellFlagged):
            reveal_cell(attempt.pk, row, col)

        attempt.refresh_from_db()
        assert attempt.board == original
        assert attempt.board["cells"][row][col]["revealed"] is False
        assert attempt.board["cells"][row][col]["flagged"] is True

    @pytest.mark.parametrize("status", [MinesweeperStatus.WON, MinesweeperStatus.LOST])
    def test_finished_attempt_rejects_reveal(self, team, node, status):
        attempt = _playing(team, node)
        game = attempt.game
        row, col = _find_cell(game, attempt, mine=False)
        _finish(attempt, status)
        original = copy.deepcopy(attempt.board)

        with pytest.raises(GameFinished):
            reveal_cell(attempt.pk, row, col)

        attempt.refresh_from_db()
        assert attempt.board == original
        assert attempt.status == status


class TestFloodFill:
    def test_zero_cell_expands_connected_region_and_boundary(self, team, node):
        attempt = _split_attempt(team, node)
        original = copy.deepcopy(attempt.board)
        original_layout = copy.deepcopy(attempt.game.board)

        updated = reveal_cell(attempt.pk, 0, 0)
        revealed = _revealed(updated.board)

        assert (0, 0) in revealed
        assert (2, 2) in revealed
        assert (0, 3) in revealed
        assert (3, 3) in revealed
        assert (0, 4) not in revealed
        assert (8, 8) not in revealed
        assert (0, 5) not in revealed
        assert (8, 7) not in revealed

        for row, col in revealed:
            cell = updated.board["cells"][row][col]
            before = original["cells"][row][col]
            assert cell["flagged"] is False
            assert cell["flagged"] == before["flagged"]
            assert original_layout["cells"][row][col]["mine"] is False

        for row, line in enumerate(updated.board["cells"]):
            for col, cell in enumerate(line):
                if (row, col) in revealed:
                    continue
                assert cell == original["cells"][row][col]

        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.board == updated.board
        assert stored.status == MinesweeperStatus.IN_PROGRESS
        stored.game.refresh_from_db()
        assert stored.game.board == original_layout

    def test_numbered_cell_does_not_expand(self, team, node):
        attempt = _split_attempt(team, node)
        original = copy.deepcopy(attempt.board)

        updated = reveal_cell(attempt.pk, 0, 3)
        assert _revealed(updated.board) == {(0, 3)}
        assert attempt.game.board["cells"][0][3]["adjacent_mines"] > 0
        for row, line in enumerate(updated.board["cells"]):
            for col, cell in enumerate(line):
                if (row, col) == (0, 3):
                    continue
                assert cell == original["cells"][row][col]

    def test_mine_does_not_expand(self, team, node):
        attempt = _split_attempt(team, node)
        original = copy.deepcopy(attempt.board)

        updated = reveal_cell(attempt.pk, 0, 4)
        assert _revealed(updated.board) == {(0, 4)}
        assert attempt.game.board["cells"][0][4]["mine"] is True
        assert updated.status == MinesweeperStatus.LOST
        assert updated.score == 0
        assert updated.finished_at is not None
        for row, line in enumerate(updated.board["cells"]):
            for col, cell in enumerate(line):
                if (row, col) == (0, 4):
                    continue
                assert cell == original["cells"][row][col]

    def test_flagged_cell_blocks_direct_reveal(self, team, node):
        attempt = _split_attempt(team, node, flags=frozenset({(0, 0)}))
        original = copy.deepcopy(attempt.board)

        with pytest.raises(CellFlagged):
            reveal_cell(attempt.pk, 0, 0)

        attempt.refresh_from_db()
        assert attempt.board == original

    def test_flagged_cell_is_skipped_during_flood_fill(self, team, node):
        attempt = _split_attempt(team, node, flags=frozenset({(0, 1)}))
        original_flag = copy.deepcopy(attempt.board["cells"][0][1])

        updated = reveal_cell(attempt.pk, 0, 0)
        flagged = updated.board["cells"][0][1]
        revealed = _revealed(updated.board)

        assert flagged == original_flag
        assert flagged["revealed"] is False
        assert flagged["flagged"] is True
        assert (0, 0) in revealed
        assert (0, 2) in revealed
        assert (0, 1) not in revealed

    def test_already_revealed_cells_are_not_mutated_by_flood_fill(self, team, node):
        attempt = _split_attempt(team, node)
        _patch_progress(attempt, 1, 1, revealed=True)
        snapshot = copy.deepcopy(attempt.board["cells"][1][1])

        updated = reveal_cell(attempt.pk, 0, 0)
        assert updated.board["cells"][1][1] == snapshot
        assert (0, 0) in _revealed(updated.board)
        assert (2, 2) in _revealed(updated.board)

    def test_corner_zero_stays_in_bounds(self, team, node):
        attempt = _split_attempt(team, node)
        updated = reveal_cell(attempt.pk, 0, 0)
        revealed = _revealed(updated.board)
        assert (0, 0) in revealed
        assert all(0 <= row < 9 and 0 <= col < 9 for row, col in revealed)
        assert updated.status == MinesweeperStatus.IN_PROGRESS

    def test_edge_zero_stays_in_bounds(self, team, node):
        attempt = _split_attempt(team, node)
        updated = reveal_cell(attempt.pk, 0, 2)
        revealed = _revealed(updated.board)
        assert (0, 2) in revealed
        assert (0, 0) in revealed
        assert (0, 5) not in revealed
        assert all(0 <= row < 9 and 0 <= col < 9 for row, col in revealed)

    def test_flooding_every_safe_cell_does_not_mark_a_win(self, team, node):
        attempt = _split_attempt(team, node)
        updated = reveal_cell(attempt.pk, 0, 0)
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.score == 0
        assert updated.finished_at is None


@pytest.mark.postgres_only
@pytest.mark.django_db(transaction=True)
class TestRevealConcurrency:
    def test_concurrent_reveals_both_persist(self, team, node):
        attempt = _split_attempt(team, node)
        targets = [(0, 3), (8, 3)]
        barrier = threading.Barrier(len(targets))
        errors = []

        def reveal(coords):
            barrier.wait()
            try:
                reveal_cell(attempt.pk, *coords)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                errors.append(f"{coords}: {exc!r}")
            finally:
                connection.close()

        threads = [threading.Thread(target=reveal, args=(coords,)) for coords in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors, errors
        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        for row, col in targets:
            assert stored.board["cells"][row][col]["revealed"] is True


class TestToggleFlag:
    def test_flags_an_unrevealed_cell(self, team, node):
        attempt = _split_attempt(team, node)
        original = copy.deepcopy(attempt.board)
        original_layout = copy.deepcopy(attempt.game.board)

        updated = toggle_flag(attempt.pk, 0, 0)
        cell = updated.board["cells"][0][0]

        assert cell["flagged"] is True
        assert cell["revealed"] is False
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.score == 0
        assert updated.finished_at is None
        for row, line in enumerate(updated.board["cells"]):
            for col, other in enumerate(line):
                if (row, col) == (0, 0):
                    continue
                assert other == original["cells"][row][col]

        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.board["cells"][0][0]["flagged"] is True
        stored.game.refresh_from_db()
        assert stored.game.board == original_layout

    def test_unflags_a_flagged_cell(self, team, node):
        attempt = _split_attempt(team, node, flags=frozenset({(0, 0)}))
        updated = toggle_flag(attempt.pk, 0, 0)
        assert updated.board["cells"][0][0]["flagged"] is False
        assert updated.board["cells"][0][0]["revealed"] is False

    def test_revealed_cell_cannot_be_flagged(self, team, node):
        attempt = _split_attempt(team, node)
        reveal_cell(attempt.pk, 0, 3)
        original = copy.deepcopy(MinesweeperAttempt.objects.get(pk=attempt.pk).board)

        with pytest.raises(CannotFlagRevealed):
            toggle_flag(attempt.pk, 0, 3)

        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.board == original

    @pytest.mark.parametrize(("row", "col"), [(-1, 0), (0, -1), (9, 0), (0, 9), (100, 0)])
    def test_invalid_coordinates_leave_the_board_unchanged(self, team, node, row, col):
        attempt = _split_attempt(team, node)
        original = copy.deepcopy(attempt.board)

        with pytest.raises(InvalidCell):
            toggle_flag(attempt.pk, row, col)

        attempt.refresh_from_db()
        assert attempt.board == original

    @pytest.mark.parametrize("status", [MinesweeperStatus.WON, MinesweeperStatus.LOST])
    def test_finished_attempt_rejects_flag(self, team, node, status):
        attempt = _split_attempt(team, node)
        _finish(attempt, status)
        original = copy.deepcopy(attempt.board)

        with pytest.raises(GameFinished):
            toggle_flag(attempt.pk, 0, 0)

        attempt.refresh_from_db()
        assert attempt.board == original

    def test_flagging_all_mines_does_not_win(self, team, node):
        attempt = _split_attempt(team, node, flags=SPLIT_MINES)
        assert attempt.status == MinesweeperStatus.IN_PROGRESS
        updated = toggle_flag(attempt.pk, 0, 0)
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.score == 0
        assert updated.finished_at is None


class TestLoss:
    def test_clicked_mine_loses_without_flood_fill(self, team, node):
        attempt = _split_attempt(team, node)
        original = copy.deepcopy(attempt.board)

        updated = reveal_cell(attempt.pk, 0, 4)
        assert updated.status == MinesweeperStatus.LOST
        assert updated.score == 0
        assert updated.finished_at is not None
        assert updated.board["cells"][0][4]["revealed"] is True
        assert _revealed(updated.board) == {(0, 4)}
        for row, line in enumerate(updated.board["cells"]):
            for col, cell in enumerate(line):
                if (row, col) == (0, 4):
                    continue
                assert cell == original["cells"][row][col]

        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.status == MinesweeperStatus.LOST
        assert stored.score == 0

    def test_lost_attempt_rejects_reveal_and_flag(self, team, node):
        attempt = _split_attempt(team, node)
        reveal_cell(attempt.pk, 0, 4)
        original = copy.deepcopy(MinesweeperAttempt.objects.get(pk=attempt.pk).board)

        with pytest.raises(GameFinished):
            reveal_cell(attempt.pk, 0, 3)
        with pytest.raises(GameFinished):
            toggle_flag(attempt.pk, 0, 0)

        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.board == original
        assert stored.status == MinesweeperStatus.LOST


class TestWin:
    def test_last_safe_cell_wins_and_leaves_mines_hidden(self, team, node, monkeypatch):
        started = timezone.now()
        attempt = _split_attempt(team, node)
        MinesweeperAttempt.objects.filter(pk=attempt.pk).update(started_at=started)
        _reveal_all_safe_except(attempt, {(0, 3)})
        monkeypatch.setattr("minesweeper.services._now", lambda: started + timedelta(seconds=35))

        updated = reveal_cell(attempt.pk, 0, 3)
        assert updated.status == MinesweeperStatus.WON
        assert updated.finished_at == started + timedelta(seconds=35)
        assert updated.score == 165
        assert updated.board["cells"][0][3]["revealed"] is True
        for row, col in SPLIT_MINES:
            assert updated.board["cells"][row][col]["revealed"] is False

    def test_flagged_mines_alone_do_not_win(self, team, node):
        attempt = _split_attempt(team, node)
        for row, col in SPLIT_MINES:
            toggle_flag(attempt.pk, row, col)
        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.status == MinesweeperStatus.IN_PROGRESS
        assert stored.finished_at is None

    def test_unrevealed_safe_cell_prevents_a_win(self, team, node):
        attempt = _split_attempt(team, node)
        updated = reveal_cell(attempt.pk, 0, 3)
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.finished_at is None

    def test_incorrectly_flagged_safe_cell_prevents_a_win(self, team, node):
        attempt = _split_attempt(team, node, flags=frozenset({(0, 0)}))
        _reveal_all_safe_except(attempt, {(0, 0)})
        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.status == MinesweeperStatus.IN_PROGRESS
        with pytest.raises(CellFlagged):
            reveal_cell(attempt.pk, 0, 0)
        stored.refresh_from_db()
        assert stored.status == MinesweeperStatus.IN_PROGRESS
        assert stored.board["cells"][0][0]["revealed"] is False
        assert stored.board["cells"][0][0]["flagged"] is True

    def test_flood_fill_of_remaining_zeros_wins(self, team, node):
        attempt = _split_attempt(team, node)
        remaining = {(0, 0), (0, 1)}
        _reveal_all_safe_except(attempt, remaining)
        updated = reveal_cell(attempt.pk, 0, 0)
        assert updated.status == MinesweeperStatus.WON
        assert (0, 1) in _revealed(updated.board)
        assert updated.finished_at is not None

    def test_won_attempt_rejects_reveal_and_flag(self, team, node):
        attempt = _split_attempt(team, node)
        _reveal_all_safe_except(attempt, {(0, 3)})
        reveal_cell(attempt.pk, 0, 3)
        original = copy.deepcopy(MinesweeperAttempt.objects.get(pk=attempt.pk).board)

        with pytest.raises(GameFinished):
            reveal_cell(attempt.pk, 0, 4)
        with pytest.raises(GameFinished):
            toggle_flag(attempt.pk, 8, 8)

        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert stored.board == original
        assert stored.status == MinesweeperStatus.WON


class TestScoring:
    @pytest.mark.parametrize(
        ("difficulty", "elapsed", "expected"),
        [
            (MinesweeperDifficulty.EASY, 35, 165),
            (MinesweeperDifficulty.EASY, 100, 100),
            (MinesweeperDifficulty.MEDIUM, 60, 440),
            (MinesweeperDifficulty.HARD, 10, 990),
            (MinesweeperDifficulty.EASY, 10_000, 100),
        ],
    )
    def test_win_score_uses_base_plus_time_bonus(
        self, team, node, monkeypatch, difficulty, elapsed, expected
    ):
        started = timezone.now()
        attempt = _prepared_attempt(team, node, difficulty)
        MinesweeperAttempt.objects.filter(pk=attempt.pk).update(started_at=started)
        _reveal_all_safe_except(attempt, {(0, 0)})
        monkeypatch.setattr(
            "minesweeper.services._now", lambda: started + timedelta(seconds=elapsed)
        )

        updated = reveal_cell(attempt.pk, 0, 0)
        assert updated.status == MinesweeperStatus.WON
        assert updated.score == expected
        assert updated.score == DIFFICULTY_BASE_SCORES[difficulty] + max(
            0, DIFFICULTY_BASE_SCORES[difficulty] - elapsed
        )

    def test_loss_score_is_zero(self, team, node, monkeypatch):
        started = timezone.now()
        attempt = _prepared_attempt(team, node, MinesweeperDifficulty.HARD)
        MinesweeperAttempt.objects.filter(pk=attempt.pk).update(started_at=started)
        mine = next(iter(_cluster_mines(MinesweeperDifficulty.HARD)))
        monkeypatch.setattr("minesweeper.services._now", lambda: started + timedelta(seconds=5))

        updated = reveal_cell(attempt.pk, *mine)
        assert updated.status == MinesweeperStatus.LOST
        assert updated.score == 0


@pytest.mark.postgres_only
@pytest.mark.django_db(transaction=True)
class TestToggleFlagConcurrency:
    def test_concurrent_flags_both_persist(self, team, node):
        attempt = _split_attempt(team, node)
        targets = [(0, 0), (8, 3)]
        barrier = threading.Barrier(len(targets))
        errors = []

        def flag(coords):
            barrier.wait()
            try:
                toggle_flag(attempt.pk, *coords)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                errors.append(f"{coords}: {exc!r}")
            finally:
                connection.close()

        threads = [threading.Thread(target=flag, args=(coords,)) for coords in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors, errors
        stored = MinesweeperAttempt.objects.get(pk=attempt.pk)
        for row, col in targets:
            assert stored.board["cells"][row][col]["flagged"] is True


@pytest.mark.postgres_only
@pytest.mark.django_db(transaction=True)
class TestStartPlayConcurrency:
    @pytest.fixture(autouse=True)
    def _reachable(self, team, other_team, node):
        grant_access(team, node)
        grant_access(other_team, node)

    def test_concurrent_starts_create_independent_games(self, team, other_team, node):
        _configure(node, MinesweeperDifficulty.EASY)
        barrier = threading.Barrier(2)
        ids = []
        errors = []

        def start(candidate):
            barrier.wait()
            try:
                ids.append(start_play(node, candidate).pk)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                errors.append(f"{candidate.code}: {exc!r}")
            finally:
                connection.close()

        threads = [
            threading.Thread(target=start, args=(candidate,)) for candidate in (team, other_team)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors, errors
        assert len(ids) == 2
        assert len(set(ids)) == 2
        assert MinesweeperGame.objects.filter(node=node).count() == 2
        assert MinesweeperAttempt.objects.filter(status=MinesweeperStatus.IN_PROGRESS).count() == 2

    def test_concurrent_starts_from_the_same_team_resume_one_attempt(self, team, node):
        _configure(node, MinesweeperDifficulty.EASY)
        barrier = threading.Barrier(2)
        ids = []
        errors = []

        def start():
            barrier.wait()
            try:
                ids.append(start_play(node, team).pk)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=start) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors, errors
        assert len(ids) == 2
        assert len(set(ids)) == 1
        assert MinesweeperGame.objects.filter(node=node).count() == 1
        assert (
            MinesweeperAttempt.objects.filter(
                team=team, status=MinesweeperStatus.IN_PROGRESS
            ).count()
            == 1
        )
