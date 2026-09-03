"""HTTP layer over Minesweeper services — auth, ownership, sanitization."""

import copy

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from game.models import GameSettings, GameStatus, LevelConfig, Node
from minesweeper.models import (
    DIFFICULTY_LAYOUTS,
    MinesweeperDifficulty,
    MinesweeperGame,
    MinesweeperStatus,
)
from minesweeper.services import assign_game_to_team, create_game, reveal_cell
from teams.models import Team

pytestmark = pytest.mark.django_db
User = get_user_model()

CREATE_URL = "/api/minesweeper/games/"

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

# 9×9 / 10 mines: column-4 wall isolates the left from the right.
SPLIT_MINES = frozenset((row, 4) for row in range(9)) | frozenset({(8, 8)})


def _detail(pk):
    return f"/api/minesweeper/games/{pk}/"


def _join(pk):
    return f"/api/minesweeper/games/{pk}/join/"


def _reveal(pk):
    return f"/api/minesweeper/games/{pk}/reveal/"


def _flag(pk):
    return f"/api/minesweeper/games/{pk}/flag/"


@pytest.fixture
def running_contest():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture
def alpha():
    return Team.objects.create(code="alpha", name="Alpha")


@pytest.fixture
def beta():
    return Team.objects.create(code="beta", name="Beta")


@pytest.fixture
def node():
    return Node.objects.create(
        code="ms1",
        name="MS 1",
        level=LevelConfig.objects.get(level="easy"),
    )


@pytest.fixture
def alpha_user(alpha):
    return User.objects.create_user("alpha-user", password="pw", team=alpha)


@pytest.fixture
def beta_user(beta):
    return User.objects.create_user("beta-user", password="pw", team=beta)


@pytest.fixture
def alpha_client(alpha_user):
    client = APIClient()
    client.force_authenticate(user=alpha_user)
    return client


@pytest.fixture
def beta_client(beta_user):
    client = APIClient()
    client.force_authenticate(user=beta_user)
    return client


@pytest.fixture
def mentor():
    user = User.objects.create_user("mentor", password="pw")
    user.groups.add(Group.objects.get(name="Mentors"))
    return user


@pytest.fixture
def staff_user():
    return User.objects.create_user("staff", password="pw", is_staff=True)


@pytest.fixture
def staff_client(staff_user):
    client = APIClient()
    client.force_authenticate(user=staff_user)
    return client


def _adjacent_from_mines(mines, row, col, *, width, height) -> int:
    count = 0
    for d_row, d_col in _NEIGHBOR_OFFSETS:
        n_row, n_col = row + d_row, col + d_col
        if 0 <= n_row < height and 0 <= n_col < width and (n_row, n_col) in mines:
            count += 1
    return count


def _install_board(game, mines, flags=frozenset()):
    width, height = game.width, game.height
    game.board = {
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
    game.save(update_fields=["board"])
    game.refresh_from_db()


def _unclaimed(node, difficulty=MinesweeperDifficulty.EASY):
    return create_game(node, difficulty)


def _claimed(team, node, difficulty=MinesweeperDifficulty.EASY):
    game = create_game(node, difficulty)
    return assign_game_to_team(game.pk, team)


def _split_game(team, node):
    game = _claimed(team, node)
    _install_board(game, SPLIT_MINES)
    return game


def _reveal_all_safe_except(game, except_cells):
    board = copy.deepcopy(game.board)
    for row, line in enumerate(board["cells"]):
        for col, cell in enumerate(line):
            if not cell["mine"] and (row, col) not in except_cells:
                cell["revealed"] = True
    game.board = board
    game.save(update_fields=["board"])
    game.refresh_from_db()


def _assert_no_hidden_mines(board):
    for row in board["cells"]:
        for cell in row:
            assert "mine" not in cell
            if cell["revealed"]:
                assert "adjacent_mines" in cell
            else:
                assert "adjacent_mines" not in cell
                assert set(cell) == {"revealed", "flagged"}


class TestAuthentication:
    @pytest.mark.parametrize(
        "method,url_builder,payload",
        [
            ("post", lambda: CREATE_URL, {"difficulty": "easy"}),
            ("post", lambda: _join(1), None),
            ("get", lambda: _detail(1), None),
            ("post", lambda: _reveal(1), {"row": 0, "col": 0}),
            ("post", lambda: _flag(1), {"row": 0, "col": 0}),
        ],
    )
    def test_anonymous_is_rejected(self, running_contest, method, url_builder, payload):
        client = APIClient()
        kwargs = {"format": "json"} if payload is not None else {}
        response = getattr(client, method)(url_builder(), payload or {}, **kwargs)
        assert response.status_code == 403

    def test_user_without_a_team_cannot_join(self, running_contest, node):
        game = _unclaimed(node)
        user = User.objects.create_user("lone", password="pw")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(_join(game.pk), {}, format="json")
        assert response.status_code == 403

    def test_mentor_cannot_join(self, running_contest, mentor, node):
        game = _unclaimed(node)
        client = APIClient()
        client.force_authenticate(user=mentor)
        response = client.post(_join(game.pk), {}, format="json")
        assert response.status_code == 403
        assert not mentor.team_id

    def test_player_cannot_create(self, alpha_client, node, running_contest):
        response = alpha_client.post(
            CREATE_URL, {"node": node.pk, "difficulty": "easy"}, format="json"
        )
        assert response.status_code == 403
        assert MinesweeperGame.objects.count() == 0


class TestCreateGame:
    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_staff_creates_an_unclaimed_game(self, staff_client, node, difficulty):
        layout = DIFFICULTY_LAYOUTS[difficulty]
        response = staff_client.post(
            CREATE_URL,
            {"node": node.pk, "difficulty": difficulty, "team": "beta"},
            format="json",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["difficulty"] == difficulty
        assert body["node"] == node.pk
        assert body["width"] == layout["width"]
        assert body["height"] == layout["height"]
        assert body["mine_count"] == layout["mine_count"]
        assert body["status"] == MinesweeperStatus.IN_PROGRESS
        assert body["score"] == 0
        assert body["finished_at"] is None
        assert "team" not in body
        assert len(body["board"]["cells"]) == layout["height"]
        _assert_no_hidden_mines(body["board"])
        stored = MinesweeperGame.objects.get(pk=body["id"])
        assert stored.team_id is None
        assert stored.node_id == node.pk

    def test_missing_node_is_rejected(self, staff_client):
        response = staff_client.post(CREATE_URL, {"difficulty": "easy"}, format="json")
        assert response.status_code == 400
        assert "node" in response.json()

    def test_unknown_node_is_rejected(self, staff_client):
        response = staff_client.post(
            CREATE_URL, {"node": 999_999, "difficulty": "easy"}, format="json"
        )
        assert response.status_code == 400
        assert "node" in response.json()

    def test_invalid_difficulty_is_rejected(self, staff_client, node):
        response = staff_client.post(
            CREATE_URL, {"node": node.pk, "difficulty": "expert"}, format="json"
        )
        assert response.status_code == 400
        assert "difficulty" in response.json()

    def test_staff_can_create_when_contest_is_not_running(
        self, staff_client, node, running_contest
    ):
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = staff_client.post(
            CREATE_URL, {"node": node.pk, "difficulty": "easy"}, format="json"
        )
        assert response.status_code == 201
        stored = MinesweeperGame.objects.get(pk=response.json()["id"])
        assert stored.team_id is None


class TestJoinGame:
    def test_assigns_the_authenticated_team(self, alpha_client, alpha, node, running_contest):
        game = _unclaimed(node)
        response = alpha_client.post(_join(game.pk), {}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == game.pk
        assert body["node"] == node.pk
        assert body["status"] == MinesweeperStatus.IN_PROGRESS
        assert "team" not in body
        _assert_no_hidden_mines(body["board"])
        game.refresh_from_db()
        assert game.team_id == alpha.pk

    def test_same_team_join_is_idempotent(self, alpha_client, alpha, node, running_contest):
        game = _unclaimed(node)
        first = alpha_client.post(_join(game.pk), {}, format="json")
        second = alpha_client.post(_join(game.pk), {}, format="json")
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["id"] == game.pk
        game.refresh_from_db()
        assert game.team_id == alpha.pk

    def test_other_team_cannot_claim(self, alpha, beta_client, node, running_contest):
        game = _claimed(alpha, node)
        response = beta_client.post(_join(game.pk), {}, format="json")
        assert response.status_code == 409
        assert response.json()["detail"] == "این بازی قبلاً گرفته شده است."
        game.refresh_from_db()
        assert game.team_id == alpha.pk

    def test_missing_game_is_404(self, alpha_client, running_contest):
        response = alpha_client.post(_join(999_999), {}, format="json")
        assert response.status_code == 404
        assert response.json() == {"detail": "بازی پیدا نشد."}

    def test_join_rejected_when_contest_is_not_running(self, alpha_client, node, running_contest):
        game = _unclaimed(node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.post(_join(game.pk), {}, format="json")
        assert response.status_code == 403
        game.refresh_from_db()
        assert game.team_id is None

    def test_join_then_reveal(self, alpha_client, alpha, node, running_contest):
        game = _unclaimed(node)
        _install_board(game, SPLIT_MINES)
        joined = alpha_client.post(_join(game.pk), {}, format="json")
        assert joined.status_code == 200
        assert joined.json()["id"] == game.pk
        game.refresh_from_db()
        assert game.team_id == alpha.pk
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        cell = response.json()["board"]["cells"][0][3]
        assert cell["revealed"] is True
        _assert_no_hidden_mines(response.json()["board"])


class TestGameDetail:
    def test_owner_can_read_sanitized_board(
        self, alpha, node, alpha_client, running_contest, monkeypatch
    ):
        def first_k(population, k):
            return population[:k]

        monkeypatch.setattr("minesweeper.services.random.sample", first_k)
        game = _claimed(alpha, node)

        response = alpha_client.get(_detail(game.pk))
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == game.pk
        assert body["node"] == node.pk
        _assert_no_hidden_mines(body["board"])
        # Known mine at (0, 0) is indistinguishable from any other unrevealed cell.
        assert body["board"]["cells"][0][0] == {"revealed": False, "flagged": False}
        assert body["board"]["cells"][8][8] == {"revealed": False, "flagged": False}

    def test_missing_game_is_404(self, alpha_client, running_contest):
        response = alpha_client.get(_detail(999_999))
        assert response.status_code == 404

    def test_unclaimed_game_is_404(self, alpha_client, node, running_contest):
        game = _unclaimed(node)
        response = alpha_client.get(_detail(game.pk))
        assert response.status_code == 404
        assert response.json() == alpha_client.get(_detail(999_999)).json()

    def test_other_team_gets_404(self, alpha, node, alpha_client, beta_client, running_contest):
        game = _claimed(alpha, node)
        response = beta_client.get(_detail(game.pk))
        assert response.status_code == 404
        assert response.json() == alpha_client.get(_detail(999_999)).json()

    def test_revealed_cell_exposes_adjacent_not_mine(
        self, alpha, node, alpha_client, running_contest
    ):
        game = _split_game(alpha, node)
        reveal_cell(game.pk, 0, 3)
        response = alpha_client.get(_detail(game.pk))
        assert response.status_code == 200
        cell = response.json()["board"]["cells"][0][3]
        assert cell["revealed"] is True
        assert "adjacent_mines" in cell
        assert "mine" not in cell
        _assert_no_hidden_mines(response.json()["board"])

    def test_finished_game_exposes_mines(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        reveal_cell(game.pk, 0, 4)
        response = alpha_client.get(_detail(game.pk))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.LOST
        mine = body["board"]["cells"][0][4]
        assert mine["mine"] is True
        assert mine["revealed"] is True
        hidden_mine = body["board"]["cells"][8][8]
        assert hidden_mine["mine"] is True
        assert hidden_mine["revealed"] is False

    def test_get_allowed_when_contest_is_not_running(
        self, alpha, node, alpha_client, running_contest
    ):
        game = _claimed(alpha, node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.get(_detail(game.pk))
        assert response.status_code == 200


class TestTeamIsolation:
    def test_other_team_cannot_reveal_or_flag(self, alpha, node, beta_client, running_contest):
        game = _split_game(alpha, node)
        assert (
            beta_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json").status_code
            == 404
        )
        assert (
            beta_client.post(_flag(game.pk), {"row": 0, "col": 0}, format="json").status_code == 404
        )
        game.refresh_from_db()
        assert game.board["cells"][0][3]["revealed"] is False
        assert game.board["cells"][0][0]["flagged"] is False


class TestRevealApi:
    def test_safe_reveal(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.IN_PROGRESS
        assert body["score"] == 0
        assert body["finished_at"] is None
        cell = body["board"]["cells"][0][3]
        assert cell["revealed"] is True
        assert "mine" not in cell
        _assert_no_hidden_mines(body["board"])

    def test_invalid_coordinates(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        response = alpha_client.post(_reveal(game.pk), {"row": -1, "col": 0}, format="json")
        assert response.status_code == 422

    def test_already_revealed(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 409

    def test_flagged_cell(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        alpha_client.post(_flag(game.pk), {"row": 0, "col": 0}, format="json")
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 409

    def test_mine_causes_loss(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 4}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.LOST
        assert body["score"] == 0
        assert body["finished_at"] is not None
        assert body["board"]["cells"][0][4]["mine"] is True

    def test_win_after_final_safe_cell(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        _reveal_all_safe_except(game, {(0, 3)})
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.WON
        assert body["score"] > 0
        assert body["finished_at"] is not None
        assert body["board"]["cells"][0][4]["mine"] is True

    def test_flood_fill_response(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 200
        cells = response.json()["board"]["cells"]
        assert cells[0][0]["revealed"] is True
        assert cells[2][2]["revealed"] is True
        assert cells[0][5]["revealed"] is False
        assert response.json()["status"] == MinesweeperStatus.IN_PROGRESS
        _assert_no_hidden_mines(response.json()["board"])

    def test_finished_game_rejects_reveal(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        alpha_client.post(_reveal(game.pk), {"row": 0, "col": 4}, format="json")
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 409

    def test_reveal_rejected_when_contest_is_not_running(
        self, alpha, node, alpha_client, running_contest
    ):
        game = _split_game(alpha, node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 403


class TestFlagApi:
    def test_flag_and_unflag(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        flagged = alpha_client.post(_flag(game.pk), {"row": 0, "col": 0}, format="json")
        assert flagged.status_code == 200
        cell = flagged.json()["board"]["cells"][0][0]
        assert cell == {"revealed": False, "flagged": True}
        assert flagged.json()["status"] == MinesweeperStatus.IN_PROGRESS
        assert flagged.json()["score"] == 0

        unflagged = alpha_client.post(_flag(game.pk), {"row": 0, "col": 0}, format="json")
        assert unflagged.json()["board"]["cells"][0][0] == {"revealed": False, "flagged": False}

    def test_revealed_cell_cannot_be_flagged(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        response = alpha_client.post(_flag(game.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 409

    def test_invalid_coordinates(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        response = alpha_client.post(_flag(game.pk), {"row": 9, "col": 0}, format="json")
        assert response.status_code == 422

    def test_finished_game_rejects_flag(self, alpha, node, alpha_client, running_contest):
        game = _split_game(alpha, node)
        alpha_client.post(_reveal(game.pk), {"row": 0, "col": 4}, format="json")
        response = alpha_client.post(_flag(game.pk), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 409

    def test_flag_rejected_when_contest_is_not_running(
        self, alpha, node, alpha_client, running_contest
    ):
        game = _split_game(alpha, node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.post(_flag(game.pk), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 403
