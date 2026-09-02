"""Creating a Minesweeper game and generating its initial board."""

import pytest

from minesweeper.exceptions import InvalidDifficulty, MinesweeperServiceError
from minesweeper.models import (
    DIFFICULTY_LAYOUTS,
    MinesweeperDifficulty,
    MinesweeperGame,
    MinesweeperStatus,
)
from minesweeper.services import create_game
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
