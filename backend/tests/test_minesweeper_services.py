"""Creating a Minesweeper game, generating its board, and revealing a cell."""

import copy
import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from game.models import LevelConfig, Node
from minesweeper.exceptions import (
    CannotFlagRevealed,
    CellAlreadyRevealed,
    CellFlagged,
    GameAlreadyClaimed,
    GameFinished,
    InvalidCell,
    InvalidDifficulty,
    MinesweeperServiceError,
)
from minesweeper.models import (
    DIFFICULTY_BASE_SCORES,
    DIFFICULTY_LAYOUTS,
    MinesweeperDifficulty,
    MinesweeperGame,
    MinesweeperStatus,
)
from minesweeper.services import assign_game_to_team, create_game, reveal_cell, toggle_flag
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


def _claimed(team, node, difficulty=MinesweeperDifficulty.EASY):
    game = create_game(node, difficulty)
    return assign_game_to_team(game.pk, team)


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
    def test_creates_an_unclaimed_in_progress_game(self, node, difficulty):
        layout = DIFFICULTY_LAYOUTS[difficulty]
        game = create_game(node, difficulty)

        assert game.team_id is None
        assert game.node_id == node.pk
        assert game.difficulty == difficulty
        assert game.width == layout["width"]
        assert game.height == layout["height"]
        assert game.mine_count == layout["mine_count"]
        assert game.status == MinesweeperStatus.IN_PROGRESS
        assert game.score == 0
        assert game.finished_at is None
        assert game.started_at is not None
        assert game.created_at is not None


class TestAssignGameToTeam:
    def test_assigns_an_unclaimed_game(self, team, node):
        game = create_game(node, MinesweeperDifficulty.EASY)
        assert game.team_id is None

        claimed = assign_game_to_team(game.pk, team)

        assert claimed.pk == game.pk
        assert claimed.team_id == team.pk
        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.team_id == team.pk

    def test_same_team_is_idempotent(self, team, node):
        game = create_game(node, MinesweeperDifficulty.EASY)
        first = assign_game_to_team(game.pk, team)
        second = assign_game_to_team(game.pk, team)
        assert first.team_id == second.team_id == team.pk
        assert MinesweeperGame.objects.filter(pk=game.pk).count() == 1

    def test_other_team_cannot_claim(self, team, other_team, node):
        game = create_game(node, MinesweeperDifficulty.EASY)
        assign_game_to_team(game.pk, team)
        with pytest.raises(GameAlreadyClaimed) as caught:
            assign_game_to_team(game.pk, other_team)
        assert isinstance(caught.value, MinesweeperServiceError)
        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.team_id == team.pk

    def test_missing_game_raises(self, team):
        with pytest.raises(MinesweeperGame.DoesNotExist):
            assign_game_to_team(999_999, team)


class TestBoardGeneration:
    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_board_matches_layout_and_invariants(self, node, difficulty):
        layout = DIFFICULTY_LAYOUTS[difficulty]
        game = create_game(node, difficulty)
        cells = game.board["cells"]

        assert len(cells) == layout["height"]
        assert all(len(row) == layout["width"] for row in cells)

        mines = [cell for row in cells for cell in row if cell["mine"]]
        assert len(mines) == layout["mine_count"]

        for row_index, row in enumerate(cells):
            for col_index, cell in enumerate(row):
                assert cell["revealed"] is False
                assert cell["flagged"] is False
                assert cell["mine"] in (True, False)
                assert cell["adjacent_mines"] == _neighbor_mine_count(cells, row_index, col_index)

    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_board_is_persisted(self, node, difficulty):
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

        # (0, 0)–(0, 8) and (1, 0) are mines.
        assert cells[0][0]["mine"] is True
        assert cells[0][8]["mine"] is True
        assert cells[1][0]["mine"] is True
        assert cells[1][1]["mine"] is False

        # (1, 1) touches (0, 0), (0, 1), (0, 2), (1, 0) — four mines.
        assert cells[1][1]["adjacent_mines"] == 4
        # Bottom-right corner is empty and far from the first-row strip.
        assert cells[8][8]["mine"] is False
        assert cells[8][8]["adjacent_mines"] == 0


class TestInvalidDifficulty:
    def test_unknown_difficulty_is_rejected(self, node):
        with pytest.raises(InvalidDifficulty) as caught:
            create_game(node, "expert")
        assert isinstance(caught.value, MinesweeperServiceError)
        assert MinesweeperGame.objects.count() == 0


def _find_cell(game, *, mine: bool, min_adjacent: int | None = None):
    for row_index, row in enumerate(game.board["cells"]):
        for col_index, cell in enumerate(row):
            if cell["mine"] is not mine or cell["revealed"] or cell["flagged"]:
                continue
            if min_adjacent is not None and cell["adjacent_mines"] < min_adjacent:
                continue
            return row_index, col_index
    raise AssertionError(f"no unrevealed unflagged cell with mine={mine}")


def _patch_cell(game, row, col, **fields):
    board = copy.deepcopy(game.board)
    board["cells"][row][col].update(fields)
    game.board = board
    game.save(update_fields=["board"])
    game.refresh_from_db()


def _finish(game, status):
    game.status = status
    game.finished_at = timezone.now()
    game.save(update_fields=["status", "finished_at"])
    game.refresh_from_db()


# 9×9 / 10 mines: a mine wall in column 4 isolates the left (cols 0–3) from the right.
SPLIT_MINES = frozenset((row, 4) for row in range(9)) | frozenset({(8, 8)})


def _adjacent_from_mines(mines, row, col, *, width, height) -> int:
    count = 0
    for d_row, d_col in _NEIGHBOR_OFFSETS:
        n_row, n_col = row + d_row, col + d_col
        if 0 <= n_row < height and 0 <= n_col < width and (n_row, n_col) in mines:
            count += 1
    return count


def _make_board(width, height, mines, flags=frozenset()):
    return {
        "cells": [
            [
                {
                    "mine": (row, col) in mines,
                    "revealed": False,
                    "flagged": (row, col) in flags,
                    "adjacent_mines": _adjacent_from_mines(
                        mines, row, col, width=width, height=height
                    ),
                }
                for col in range(width)
            ]
            for row in range(height)
        ]
    }


def _install_board(game, mines, flags=frozenset()):
    assert len(mines) == game.mine_count
    game.board = _make_board(game.width, game.height, mines, flags)
    game.save(update_fields=["board"])
    game.refresh_from_db()


def _split_game(team, node, flags=frozenset()):
    game = _claimed(team, node)
    _install_board(game, SPLIT_MINES, flags)
    return game


def _revealed(board) -> set[tuple[int, int]]:
    return {
        (row, col)
        for row, line in enumerate(board["cells"])
        for col, cell in enumerate(line)
        if cell["revealed"]
    }


def _reveal_all_safe_except(game, except_cells: set[tuple[int, int]]):
    board = copy.deepcopy(game.board)
    for row, line in enumerate(board["cells"]):
        for col, cell in enumerate(line):
            if not cell["mine"] and (row, col) not in except_cells:
                cell["revealed"] = True
    game.board = board
    game.save(update_fields=["board"])
    game.refresh_from_db()


def _cluster_mines(difficulty) -> frozenset[tuple[int, int]]:
    layout = DIFFICULTY_LAYOUTS[difficulty]
    width, height, count = layout["width"], layout["height"], layout["mine_count"]
    positions = [
        (row, col) for row in range(height - 1, -1, -1) for col in range(width - 1, -1, -1)
    ]
    return frozenset(positions[:count])


def _prepared_game(team, node, difficulty):
    game = _claimed(team, node, difficulty)
    _install_board(game, _cluster_mines(difficulty))
    return game


class TestRevealCell:
    def test_reveals_a_safe_cell_and_persists(self, team, node):
        game = _claimed(team, node)
        row, col = _find_cell(game, mine=False, min_adjacent=1)
        original = copy.deepcopy(game.board)
        original_cell = original["cells"][row][col]

        updated = reveal_cell(game.pk, row, col)
        cell = updated.board["cells"][row][col]

        assert cell["revealed"] is True
        assert cell["mine"] is False
        assert cell["mine"] == original_cell["mine"]
        assert cell["flagged"] == original_cell["flagged"]
        assert cell["adjacent_mines"] == original_cell["adjacent_mines"]
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.score == 0
        assert updated.finished_at is None

        for r, board_row in enumerate(updated.board["cells"]):
            for c, other in enumerate(board_row):
                if (r, c) == (row, col):
                    continue
                assert other == original["cells"][r][c]

        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.board == updated.board
        assert stored.board["cells"][row][col]["revealed"] is True

    def test_revealing_a_mine_loses_the_game(self, team, node):
        game = _claimed(team, node)
        row, col = _find_cell(game, mine=True)

        updated = reveal_cell(game.pk, row, col)
        cell = updated.board["cells"][row][col]

        assert cell["mine"] is True
        assert cell["revealed"] is True
        assert updated.status == MinesweeperStatus.LOST
        assert updated.score == 0
        assert updated.finished_at is not None

    @pytest.mark.parametrize(
        ("row", "col"),
        [
            (-1, 0),
            (0, -1),
            (9, 0),  # row == height on easy
            (0, 9),  # col == width on easy
            (100, 100),
        ],
    )
    def test_invalid_coordinates_leave_the_board_unchanged(self, team, node, row, col):
        game = _claimed(team, node)
        original = copy.deepcopy(game.board)

        with pytest.raises(InvalidCell):
            reveal_cell(game.pk, row, col)

        game.refresh_from_db()
        assert game.board == original

    def test_already_revealed_cell_is_rejected(self, team, node):
        game = _claimed(team, node)
        row, col = _find_cell(game, mine=False)
        reveal_cell(game.pk, row, col)
        original = copy.deepcopy(MinesweeperGame.objects.get(pk=game.pk).board)

        with pytest.raises(CellAlreadyRevealed):
            reveal_cell(game.pk, row, col)

        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.board == original

    def test_flagged_cell_is_not_revealed(self, team, node):
        game = _claimed(team, node)
        row, col = _find_cell(game, mine=False)
        _patch_cell(game, row, col, flagged=True)
        original = copy.deepcopy(game.board)

        with pytest.raises(CellFlagged):
            reveal_cell(game.pk, row, col)

        game.refresh_from_db()
        assert game.board == original
        assert game.board["cells"][row][col]["revealed"] is False
        assert game.board["cells"][row][col]["flagged"] is True

    @pytest.mark.parametrize("status", [MinesweeperStatus.WON, MinesweeperStatus.LOST])
    def test_finished_game_rejects_reveal(self, team, node, status):
        game = _claimed(team, node)
        row, col = _find_cell(game, mine=False)
        _finish(game, status)
        original = copy.deepcopy(game.board)

        with pytest.raises(GameFinished):
            reveal_cell(game.pk, row, col)

        game.refresh_from_db()
        assert game.board == original
        assert game.status == status


class TestFloodFill:
    def test_zero_cell_expands_connected_region_and_boundary(self, team, node):
        game = _split_game(team, node)
        original = copy.deepcopy(game.board)

        updated = reveal_cell(game.pk, 0, 0)
        revealed = _revealed(updated.board)

        assert (0, 0) in revealed
        assert (2, 2) in revealed  # connected zero, several steps away
        assert (0, 3) in revealed  # numbered boundary against the mine wall
        assert (3, 3) in revealed
        assert (0, 4) not in revealed  # mine
        assert (8, 8) not in revealed  # mine on the far side
        assert (0, 5) not in revealed  # isolated right-side zero
        assert (8, 7) not in revealed

        for row, col in revealed:
            cell = updated.board["cells"][row][col]
            before = original["cells"][row][col]
            assert cell["mine"] is False
            assert cell["flagged"] is False
            assert cell["mine"] == before["mine"]
            assert cell["flagged"] == before["flagged"]
            assert cell["adjacent_mines"] == before["adjacent_mines"]

        for row, line in enumerate(updated.board["cells"]):
            for col, cell in enumerate(line):
                if (row, col) in revealed:
                    continue
                assert cell == original["cells"][row][col]

        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.board == updated.board
        assert stored.status == MinesweeperStatus.IN_PROGRESS
        assert stored.score == 0
        assert stored.finished_at is None

    def test_numbered_cell_does_not_expand(self, team, node):
        game = _split_game(team, node)
        original = copy.deepcopy(game.board)

        updated = reveal_cell(game.pk, 0, 3)
        assert _revealed(updated.board) == {(0, 3)}
        assert updated.board["cells"][0][3]["adjacent_mines"] > 0
        for row, line in enumerate(updated.board["cells"]):
            for col, cell in enumerate(line):
                if (row, col) == (0, 3):
                    continue
                assert cell == original["cells"][row][col]

    def test_mine_does_not_expand(self, team, node):
        game = _split_game(team, node)
        original = copy.deepcopy(game.board)

        updated = reveal_cell(game.pk, 0, 4)
        assert _revealed(updated.board) == {(0, 4)}
        assert updated.board["cells"][0][4]["mine"] is True
        assert updated.status == MinesweeperStatus.LOST
        assert updated.score == 0
        assert updated.finished_at is not None
        for row, line in enumerate(updated.board["cells"]):
            for col, cell in enumerate(line):
                if (row, col) == (0, 4):
                    continue
                assert cell == original["cells"][row][col]

    def test_flagged_cell_blocks_direct_reveal(self, team, node):
        game = _split_game(team, node, flags=frozenset({(0, 0)}))
        original = copy.deepcopy(game.board)

        with pytest.raises(CellFlagged):
            reveal_cell(game.pk, 0, 0)

        game.refresh_from_db()
        assert game.board == original

    def test_flagged_cell_is_skipped_during_flood_fill(self, team, node):
        game = _split_game(team, node, flags=frozenset({(0, 1)}))
        original_flag = copy.deepcopy(game.board["cells"][0][1])

        updated = reveal_cell(game.pk, 0, 0)
        flagged = updated.board["cells"][0][1]
        revealed = _revealed(updated.board)

        assert flagged == original_flag
        assert flagged["revealed"] is False
        assert flagged["flagged"] is True
        assert (0, 0) in revealed
        assert (0, 2) in revealed  # reached around the flag
        assert (0, 1) not in revealed

    def test_already_revealed_cells_are_not_mutated_by_flood_fill(self, team, node):
        game = _split_game(team, node)
        _patch_cell(game, 1, 1, revealed=True)
        snapshot = copy.deepcopy(game.board["cells"][1][1])

        updated = reveal_cell(game.pk, 0, 0)
        assert updated.board["cells"][1][1] == snapshot
        assert (0, 0) in _revealed(updated.board)
        assert (2, 2) in _revealed(updated.board)

    def test_corner_zero_stays_in_bounds(self, team, node):
        game = _split_game(team, node)
        updated = reveal_cell(game.pk, 0, 0)
        revealed = _revealed(updated.board)
        assert (0, 0) in revealed
        assert all(0 <= row < 9 and 0 <= col < 9 for row, col in revealed)
        assert updated.status == MinesweeperStatus.IN_PROGRESS

    def test_edge_zero_stays_in_bounds(self, team, node):
        game = _split_game(team, node)
        updated = reveal_cell(game.pk, 0, 2)
        revealed = _revealed(updated.board)
        assert (0, 2) in revealed
        assert (0, 0) in revealed
        assert (0, 5) not in revealed
        assert all(0 <= row < 9 and 0 <= col < 9 for row, col in revealed)

    def test_flooding_every_safe_cell_does_not_mark_a_win(self, team, node):
        """Right-side pocket is small; opening a left zero still must not finish."""
        game = _split_game(team, node)
        updated = reveal_cell(game.pk, 0, 0)
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.score == 0
        assert updated.finished_at is None


@pytest.mark.postgres_only
@pytest.mark.django_db(transaction=True)
class TestRevealConcurrency:
    def test_concurrent_reveals_both_persist(self, team, node):
        """Without the row lock, last-write-wins would drop one of the two cells."""
        game = _claimed(team, node)
        targets = [(0, 3), (8, 3)]
        _install_board(game, SPLIT_MINES)
        barrier = threading.Barrier(len(targets))
        errors = []

        def reveal(coords):
            barrier.wait()
            try:
                reveal_cell(game.pk, *coords)
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
        stored = MinesweeperGame.objects.get(pk=game.pk)
        for row, col in targets:
            assert stored.board["cells"][row][col]["revealed"] is True


class TestToggleFlag:
    def test_flags_an_unrevealed_cell(self, team, node):
        game = _split_game(team, node)
        original = copy.deepcopy(game.board)

        updated = toggle_flag(game.pk, 0, 0)
        cell = updated.board["cells"][0][0]

        assert cell["flagged"] is True
        assert cell["revealed"] is False
        assert cell["mine"] == original["cells"][0][0]["mine"]
        assert cell["adjacent_mines"] == original["cells"][0][0]["adjacent_mines"]
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.score == 0
        assert updated.finished_at is None
        for row, line in enumerate(updated.board["cells"]):
            for col, other in enumerate(line):
                if (row, col) == (0, 0):
                    continue
                assert other == original["cells"][row][col]

        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.board["cells"][0][0]["flagged"] is True

    def test_unflags_a_flagged_cell(self, team, node):
        game = _split_game(team, node, flags=frozenset({(0, 0)}))
        updated = toggle_flag(game.pk, 0, 0)
        assert updated.board["cells"][0][0]["flagged"] is False
        assert updated.board["cells"][0][0]["revealed"] is False

    def test_revealed_cell_cannot_be_flagged(self, team, node):
        game = _split_game(team, node)
        reveal_cell(game.pk, 0, 3)
        original = copy.deepcopy(MinesweeperGame.objects.get(pk=game.pk).board)

        with pytest.raises(CannotFlagRevealed):
            toggle_flag(game.pk, 0, 3)

        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.board == original

    @pytest.mark.parametrize(("row", "col"), [(-1, 0), (0, -1), (9, 0), (0, 9), (100, 0)])
    def test_invalid_coordinates_leave_the_board_unchanged(self, team, node, row, col):
        game = _split_game(team, node)
        original = copy.deepcopy(game.board)

        with pytest.raises(InvalidCell):
            toggle_flag(game.pk, row, col)

        game.refresh_from_db()
        assert game.board == original

    @pytest.mark.parametrize("status", [MinesweeperStatus.WON, MinesweeperStatus.LOST])
    def test_finished_game_rejects_flag(self, team, node, status):
        game = _split_game(team, node)
        _finish(game, status)
        original = copy.deepcopy(game.board)

        with pytest.raises(GameFinished):
            toggle_flag(game.pk, 0, 0)

        game.refresh_from_db()
        assert game.board == original

    def test_flagging_all_mines_does_not_win(self, team, node):
        game = _split_game(team, node, flags=SPLIT_MINES)
        assert game.status == MinesweeperStatus.IN_PROGRESS
        updated = toggle_flag(game.pk, 0, 0)
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.score == 0
        assert updated.finished_at is None


class TestLoss:
    def test_clicked_mine_loses_without_flood_fill(self, team, node):
        game = _split_game(team, node)
        original = copy.deepcopy(game.board)

        updated = reveal_cell(game.pk, 0, 4)
        assert updated.status == MinesweeperStatus.LOST
        assert updated.score == 0
        assert updated.finished_at is not None
        assert updated.board["cells"][0][4]["revealed"] is True
        assert updated.board["cells"][0][4]["mine"] is True
        assert _revealed(updated.board) == {(0, 4)}
        for row, line in enumerate(updated.board["cells"]):
            for col, cell in enumerate(line):
                if (row, col) == (0, 4):
                    continue
                assert cell == original["cells"][row][col]

        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.status == MinesweeperStatus.LOST
        assert stored.score == 0

    def test_lost_game_rejects_reveal_and_flag(self, team, node):
        game = _split_game(team, node)
        reveal_cell(game.pk, 0, 4)
        original = copy.deepcopy(MinesweeperGame.objects.get(pk=game.pk).board)

        with pytest.raises(GameFinished):
            reveal_cell(game.pk, 0, 3)
        with pytest.raises(GameFinished):
            toggle_flag(game.pk, 0, 0)

        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.board == original
        assert stored.status == MinesweeperStatus.LOST


class TestWin:
    def test_last_safe_cell_wins_and_leaves_mines_hidden(self, team, node, monkeypatch):
        started = timezone.now()
        game = _split_game(team, node)
        MinesweeperGame.objects.filter(pk=game.pk).update(started_at=started)
        _reveal_all_safe_except(game, {(0, 3)})
        monkeypatch.setattr("minesweeper.services._now", lambda: started + timedelta(seconds=35))

        updated = reveal_cell(game.pk, 0, 3)
        assert updated.status == MinesweeperStatus.WON
        assert updated.finished_at == started + timedelta(seconds=35)
        assert updated.score == 165
        assert updated.board["cells"][0][3]["revealed"] is True
        for row, col in SPLIT_MINES:
            assert updated.board["cells"][row][col]["revealed"] is False

    def test_flagged_mines_alone_do_not_win(self, team, node):
        game = _split_game(team, node)
        for row, col in SPLIT_MINES:
            toggle_flag(game.pk, row, col)
        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.status == MinesweeperStatus.IN_PROGRESS
        assert stored.finished_at is None

    def test_unrevealed_safe_cell_prevents_a_win(self, team, node):
        game = _split_game(team, node)
        updated = reveal_cell(game.pk, 0, 3)
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.finished_at is None

    def test_incorrectly_flagged_safe_cell_prevents_a_win(self, team, node):
        game = _split_game(team, node, flags=frozenset({(0, 0)}))
        _reveal_all_safe_except(game, {(0, 0)})
        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.status == MinesweeperStatus.IN_PROGRESS
        with pytest.raises(CellFlagged):
            reveal_cell(game.pk, 0, 0)
        stored.refresh_from_db()
        assert stored.status == MinesweeperStatus.IN_PROGRESS
        assert stored.board["cells"][0][0]["revealed"] is False
        assert stored.board["cells"][0][0]["flagged"] is True

    def test_flood_fill_of_remaining_zeros_wins(self, team, node):
        game = _split_game(team, node)
        remaining = {(0, 0), (0, 1)}
        _reveal_all_safe_except(game, remaining)
        updated = reveal_cell(game.pk, 0, 0)
        assert updated.status == MinesweeperStatus.WON
        assert (0, 1) in _revealed(updated.board)
        assert updated.finished_at is not None

    def test_won_game_rejects_reveal_and_flag(self, team, node):
        game = _split_game(team, node)
        _reveal_all_safe_except(game, {(0, 3)})
        reveal_cell(game.pk, 0, 3)
        original = copy.deepcopy(MinesweeperGame.objects.get(pk=game.pk).board)

        with pytest.raises(GameFinished):
            reveal_cell(game.pk, 0, 4)
        with pytest.raises(GameFinished):
            toggle_flag(game.pk, 8, 8)

        stored = MinesweeperGame.objects.get(pk=game.pk)
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
        game = _prepared_game(team, node, difficulty)
        MinesweeperGame.objects.filter(pk=game.pk).update(started_at=started)
        _reveal_all_safe_except(game, {(0, 0)})
        monkeypatch.setattr(
            "minesweeper.services._now", lambda: started + timedelta(seconds=elapsed)
        )

        updated = reveal_cell(game.pk, 0, 0)
        assert updated.status == MinesweeperStatus.WON
        assert updated.score == expected
        assert updated.score == DIFFICULTY_BASE_SCORES[difficulty] + max(
            0, DIFFICULTY_BASE_SCORES[difficulty] - elapsed
        )

    def test_loss_score_is_zero(self, team, node, monkeypatch):
        started = timezone.now()
        game = _prepared_game(team, node, MinesweeperDifficulty.HARD)
        MinesweeperGame.objects.filter(pk=game.pk).update(started_at=started)
        mine = next(iter(_cluster_mines(MinesweeperDifficulty.HARD)))
        monkeypatch.setattr("minesweeper.services._now", lambda: started + timedelta(seconds=5))

        updated = reveal_cell(game.pk, *mine)
        assert updated.status == MinesweeperStatus.LOST
        assert updated.score == 0


@pytest.mark.postgres_only
@pytest.mark.django_db(transaction=True)
class TestToggleFlagConcurrency:
    def test_concurrent_flags_both_persist(self, team, node):
        game = _claimed(team, node)
        _install_board(game, SPLIT_MINES)
        targets = [(0, 0), (8, 3)]
        barrier = threading.Barrier(len(targets))
        errors = []

        def flag(coords):
            barrier.wait()
            try:
                toggle_flag(game.pk, *coords)
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
        stored = MinesweeperGame.objects.get(pk=game.pk)
        for row, col in targets:
            assert stored.board["cells"][row][col]["flagged"] is True


@pytest.mark.postgres_only
@pytest.mark.django_db(transaction=True)
class TestAssignConcurrency:
    def test_only_one_team_claims(self, team, other_team, node):
        game = create_game(node, MinesweeperDifficulty.EASY)
        barrier = threading.Barrier(2)
        claimed_by = []
        errors = []

        def claim(candidate):
            barrier.wait()
            try:
                assign_game_to_team(game.pk, candidate)
                claimed_by.append(candidate.pk)
            except GameAlreadyClaimed:
                pass
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                errors.append(f"{candidate.code}: {exc!r}")
            finally:
                connection.close()

        threads = [
            threading.Thread(target=claim, args=(candidate,)) for candidate in (team, other_team)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors, errors
        assert len(claimed_by) == 1
        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.team_id == claimed_by[0]
        assert stored.team_id in {team.pk, other_team.pk}
