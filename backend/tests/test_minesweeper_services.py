"""Creating a Minesweeper game, generating its board, and revealing a cell."""

import copy
import threading

import pytest
from django.db import connection
from django.utils import timezone

from minesweeper.exceptions import (
    CellAlreadyRevealed,
    CellFlagged,
    GameFinished,
    InvalidCell,
    InvalidDifficulty,
    MinesweeperServiceError,
)
from minesweeper.models import (
    DIFFICULTY_LAYOUTS,
    MinesweeperDifficulty,
    MinesweeperGame,
    MinesweeperStatus,
)
from minesweeper.services import create_game, reveal_cell
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
    def test_creates_an_in_progress_game_for_the_team(self, team, difficulty):
        layout = DIFFICULTY_LAYOUTS[difficulty]
        game = create_game(team, difficulty)

        assert game.team_id == team.pk
        assert game.difficulty == difficulty
        assert game.width == layout["width"]
        assert game.height == layout["height"]
        assert game.mine_count == layout["mine_count"]
        assert game.status == MinesweeperStatus.IN_PROGRESS
        assert game.score == 0
        assert game.finished_at is None
        assert game.started_at is not None
        assert game.created_at is not None


class TestBoardGeneration:
    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_board_matches_layout_and_invariants(self, team, difficulty):
        layout = DIFFICULTY_LAYOUTS[difficulty]
        game = create_game(team, difficulty)
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
    def test_board_is_persisted(self, team, difficulty):
        game = create_game(team, difficulty)
        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.board == game.board
        assert stored.board["cells"]

    def test_adjacent_mines_for_a_known_layout(self, team, monkeypatch):
        """First ten cells (row-major) are mines — a 9×9 easy board."""

        def first_k(population, k):
            return population[:k]

        monkeypatch.setattr("minesweeper.services.random.sample", first_k)
        game = create_game(team, MinesweeperDifficulty.EASY)
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
    def test_unknown_difficulty_is_rejected(self, team):
        with pytest.raises(InvalidDifficulty) as caught:
            create_game(team, "expert")
        assert isinstance(caught.value, MinesweeperServiceError)
        assert MinesweeperGame.objects.count() == 0


def _find_cell(game, *, mine: bool):
    for row_index, row in enumerate(game.board["cells"]):
        for col_index, cell in enumerate(row):
            if cell["mine"] is mine and not cell["revealed"] and not cell["flagged"]:
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


class TestRevealCell:
    def test_reveals_a_safe_cell_and_persists(self, team):
        game = create_game(team, MinesweeperDifficulty.EASY)
        row, col = _find_cell(game, mine=False)
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

    def test_revealing_a_mine_does_not_end_the_game(self, team):
        game = create_game(team, MinesweeperDifficulty.EASY)
        row, col = _find_cell(game, mine=True)

        updated = reveal_cell(game.pk, row, col)
        cell = updated.board["cells"][row][col]

        assert cell["mine"] is True
        assert cell["revealed"] is True
        assert updated.status == MinesweeperStatus.IN_PROGRESS
        assert updated.score == 0
        assert updated.finished_at is None

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
    def test_invalid_coordinates_leave_the_board_unchanged(self, team, row, col):
        game = create_game(team, MinesweeperDifficulty.EASY)
        original = copy.deepcopy(game.board)

        with pytest.raises(InvalidCell):
            reveal_cell(game.pk, row, col)

        game.refresh_from_db()
        assert game.board == original

    def test_already_revealed_cell_is_rejected(self, team):
        game = create_game(team, MinesweeperDifficulty.EASY)
        row, col = _find_cell(game, mine=False)
        reveal_cell(game.pk, row, col)
        original = copy.deepcopy(MinesweeperGame.objects.get(pk=game.pk).board)

        with pytest.raises(CellAlreadyRevealed):
            reveal_cell(game.pk, row, col)

        stored = MinesweeperGame.objects.get(pk=game.pk)
        assert stored.board == original

    def test_flagged_cell_is_not_revealed(self, team):
        game = create_game(team, MinesweeperDifficulty.EASY)
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
    def test_finished_game_rejects_reveal(self, team, status):
        game = create_game(team, MinesweeperDifficulty.EASY)
        row, col = _find_cell(game, mine=False)
        _finish(game, status)
        original = copy.deepcopy(game.board)

        with pytest.raises(GameFinished):
            reveal_cell(game.pk, row, col)

        game.refresh_from_db()
        assert game.board == original
        assert game.status == status


@pytest.mark.postgres_only
@pytest.mark.django_db(transaction=True)
class TestRevealConcurrency:
    def test_concurrent_reveals_both_persist(self, team):
        """Without the row lock, last-write-wins would drop one of the two cells."""
        game = create_game(team, MinesweeperDifficulty.EASY)
        targets = [(0, 0), (0, 1)]
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
