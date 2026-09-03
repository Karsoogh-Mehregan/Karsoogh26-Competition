"""HTTP layer over Minesweeper services — auth, attempt isolation, sanitization."""

import copy

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from game.models import GameSettings, GameStatus, LevelConfig, Node
from minesweeper.models import (
    DIFFICULTY_LAYOUTS,
    MinesweeperAttempt,
    MinesweeperDifficulty,
    MinesweeperGame,
    MinesweeperStatus,
)
from minesweeper.services import create_game, get_or_create_attempt, reveal_cell
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


def _install_layout(game, mines):
    width, height = game.width, game.height
    game.board = {
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
    game.save(update_fields=["board"])
    game.refresh_from_db()


def _game(node, difficulty=MinesweeperDifficulty.EASY):
    return create_game(node, difficulty)


def _attempt(team, node, difficulty=MinesweeperDifficulty.EASY):
    game = create_game(node, difficulty)
    return get_or_create_attempt(game.pk, team)


def _split_attempt(team, node):
    game = create_game(node, MinesweeperDifficulty.EASY)
    _install_layout(game, SPLIT_MINES)
    return get_or_create_attempt(game.pk, team)


def _reveal_all_safe_except(attempt, except_cells):
    layout = attempt.game.board
    progress = copy.deepcopy(attempt.board)
    for row, layout_row in enumerate(layout["cells"]):
        for col, layout_cell in enumerate(layout_row):
            if not layout_cell["mine"] and (row, col) not in except_cells:
                progress["cells"][row][col]["revealed"] = True
    attempt.board = progress
    attempt.save(update_fields=["board"])
    attempt.refresh_from_db()


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
        game = _game(node)
        user = User.objects.create_user("lone", password="pw")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(_join(game.pk), {}, format="json")
        assert response.status_code == 403

    def test_mentor_cannot_join(self, running_contest, mentor, node):
        game = _game(node)
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
    def test_staff_creates_a_game_definition(self, staff_client, node, difficulty):
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
        assert "board" not in body
        assert "attempt_id" not in body
        assert "team" not in body
        stored = MinesweeperGame.objects.get(pk=body["id"])
        assert stored.node_id == node.pk
        assert MinesweeperAttempt.objects.count() == 0

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


class TestJoinGame:
    def test_creates_an_attempt_for_the_authenticated_team(
        self, alpha_client, alpha, node, running_contest
    ):
        game = _game(node)
        response = alpha_client.post(_join(game.pk), {}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == game.pk
        assert body["node"] == node.pk
        assert body["status"] == MinesweeperStatus.IN_PROGRESS
        assert "team" not in body
        assert body["attempt_id"]
        _assert_no_hidden_mines(body["board"])
        attempt = MinesweeperAttempt.objects.get(pk=body["attempt_id"])
        assert attempt.team_id == alpha.pk
        assert attempt.game_id == game.pk

    def test_same_team_rejoin_is_idempotent(self, alpha_client, alpha, node, running_contest):
        game = _game(node)
        first = alpha_client.post(_join(game.pk), {}, format="json")
        second = alpha_client.post(_join(game.pk), {}, format="json")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["attempt_id"] == second.json()["attempt_id"]
        assert MinesweeperAttempt.objects.filter(game=game, team=alpha).count() == 1

    def test_second_team_gets_its_own_attempt(
        self, alpha_client, beta_client, alpha, beta, node, running_contest
    ):
        game = _game(node)
        first = alpha_client.post(_join(game.pk), {}, format="json")
        second = beta_client.post(_join(game.pk), {}, format="json")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"] == game.pk
        assert first.json()["attempt_id"] != second.json()["attempt_id"]
        assert MinesweeperAttempt.objects.filter(game=game).count() == 2
        assert MinesweeperAttempt.objects.get(pk=first.json()["attempt_id"]).team_id == alpha.pk
        assert MinesweeperAttempt.objects.get(pk=second.json()["attempt_id"]).team_id == beta.pk

    def test_missing_game_is_404(self, alpha_client, running_contest):
        response = alpha_client.post(_join(999_999), {}, format="json")
        assert response.status_code == 404
        assert response.json() == {"detail": "بازی پیدا نشد."}

    def test_join_rejected_when_contest_is_not_running(self, alpha_client, node, running_contest):
        game = _game(node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.post(_join(game.pk), {}, format="json")
        assert response.status_code == 403
        assert not MinesweeperAttempt.objects.filter(game=game).exists()

    def test_join_then_reveal(self, alpha_client, alpha, node, running_contest):
        game = _game(node)
        _install_layout(game, SPLIT_MINES)
        joined = alpha_client.post(_join(game.pk), {}, format="json")
        assert joined.status_code == 200
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        cell = response.json()["board"]["cells"][0][3]
        assert cell["revealed"] is True
        _assert_no_hidden_mines(response.json()["board"])
        attempt = MinesweeperAttempt.objects.get(team=alpha, game=game)
        assert attempt.board["cells"][0][3]["revealed"] is True


class TestGameDetail:
    def test_owner_can_read_sanitized_board(
        self, alpha, node, alpha_client, running_contest, monkeypatch
    ):
        def first_k(population, k):
            return population[:k]

        monkeypatch.setattr("minesweeper.services.random.sample", first_k)
        attempt = _attempt(alpha, node)

        response = alpha_client.get(_detail(attempt.game_id))
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == attempt.game_id
        assert body["attempt_id"] == attempt.pk
        assert body["node"] == node.pk
        _assert_no_hidden_mines(body["board"])
        assert body["board"]["cells"][0][0] == {"revealed": False, "flagged": False}
        assert body["board"]["cells"][8][8] == {"revealed": False, "flagged": False}

    def test_missing_game_is_404(self, alpha_client, running_contest):
        response = alpha_client.get(_detail(999_999))
        assert response.status_code == 404

    def test_game_without_an_attempt_is_404(self, alpha_client, node, running_contest):
        game = _game(node)
        response = alpha_client.get(_detail(game.pk))
        assert response.status_code == 404
        assert response.json() == alpha_client.get(_detail(999_999)).json()

    def test_other_team_cannot_read_this_attempt(
        self, alpha, node, alpha_client, beta_client, running_contest
    ):
        attempt = _attempt(alpha, node)
        response = beta_client.get(_detail(attempt.game_id))
        assert response.status_code == 404
        assert response.json() == alpha_client.get(_detail(999_999)).json()

    def test_revealed_cell_exposes_adjacent_not_mine(
        self, alpha, node, alpha_client, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        reveal_cell(attempt.pk, 0, 3)
        response = alpha_client.get(_detail(attempt.game_id))
        assert response.status_code == 200
        cell = response.json()["board"]["cells"][0][3]
        assert cell["revealed"] is True
        assert "adjacent_mines" in cell
        assert "mine" not in cell
        _assert_no_hidden_mines(response.json()["board"])

    def test_finished_attempt_exposes_mines(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        reveal_cell(attempt.pk, 0, 4)
        response = alpha_client.get(_detail(attempt.game_id))
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
        attempt = _attempt(alpha, node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.get(_detail(attempt.game_id))
        assert response.status_code == 200


class TestTeamIsolation:
    def test_other_team_cannot_reveal_or_flag_without_joining(
        self, alpha, node, beta_client, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        game_id = attempt.game_id
        assert (
            beta_client.post(_reveal(game_id), {"row": 0, "col": 3}, format="json").status_code
            == 404
        )
        assert (
            beta_client.post(_flag(game_id), {"row": 0, "col": 0}, format="json").status_code == 404
        )
        attempt.refresh_from_db()
        assert attempt.board["cells"][0][3]["revealed"] is False
        assert attempt.board["cells"][0][0]["flagged"] is False

    def test_reveal_only_changes_the_current_team_attempt(
        self, alpha, beta, node, alpha_client, beta_client, running_contest
    ):
        game = _game(node)
        _install_layout(game, SPLIT_MINES)
        alpha_client.post(_join(game.pk), {}, format="json")
        beta_client.post(_join(game.pk), {}, format="json")
        response = alpha_client.post(_reveal(game.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        assert response.json()["board"]["cells"][0][3]["revealed"] is True

        beta_view = beta_client.get(_detail(game.pk))
        assert beta_view.status_code == 200
        assert beta_view.json()["board"]["cells"][0][3]["revealed"] is False
        assert beta_view.json()["attempt_id"] != response.json()["attempt_id"]

        alpha_attempt = MinesweeperAttempt.objects.get(game=game, team=alpha)
        beta_attempt = MinesweeperAttempt.objects.get(game=game, team=beta)
        assert alpha_attempt.board["cells"][0][3]["revealed"] is True
        assert beta_attempt.board["cells"][0][3]["revealed"] is False

    def test_finished_attempt_does_not_block_another_team(
        self, alpha, beta_client, node, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        reveal_cell(attempt.pk, 0, 4)
        attempt.refresh_from_db()
        assert attempt.status == MinesweeperStatus.LOST

        response = beta_client.post(_join(attempt.game_id), {}, format="json")
        assert response.status_code == 200
        assert response.json()["status"] == MinesweeperStatus.IN_PROGRESS
        assert response.json()["attempt_id"] != attempt.pk
        _assert_no_hidden_mines(response.json()["board"])


class TestRevealApi:
    def test_safe_reveal(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 3}, format="json")
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
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_reveal(attempt.game_id), {"row": -1, "col": 0}, format="json")
        assert response.status_code == 422

    def test_already_revealed(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 3}, format="json")
        response = alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 409

    def test_flagged_cell(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_flag(attempt.game_id), {"row": 0, "col": 0}, format="json")
        response = alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 409

    def test_mine_causes_loss(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 4}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.LOST
        assert body["score"] == 0
        assert body["finished_at"] is not None
        assert body["board"]["cells"][0][4]["mine"] is True

    def test_win_after_final_safe_cell(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        _reveal_all_safe_except(attempt, {(0, 3)})
        response = alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.WON
        assert body["score"] > 0
        assert body["finished_at"] is not None
        assert body["board"]["cells"][0][4]["mine"] is True

    def test_flood_fill_response(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 200
        cells = response.json()["board"]["cells"]
        assert cells[0][0]["revealed"] is True
        assert cells[2][2]["revealed"] is True
        assert cells[0][5]["revealed"] is False
        assert response.json()["status"] == MinesweeperStatus.IN_PROGRESS
        _assert_no_hidden_mines(response.json()["board"])

    def test_finished_attempt_rejects_reveal(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 4}, format="json")
        response = alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 409

    def test_reveal_rejected_when_contest_is_not_running(
        self, alpha, node, alpha_client, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 403


class TestFlagApi:
    def test_flag_and_unflag(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        flagged = alpha_client.post(_flag(attempt.game_id), {"row": 0, "col": 0}, format="json")
        assert flagged.status_code == 200
        cell = flagged.json()["board"]["cells"][0][0]
        assert cell == {"revealed": False, "flagged": True}
        assert flagged.json()["status"] == MinesweeperStatus.IN_PROGRESS
        assert flagged.json()["score"] == 0

        unflagged = alpha_client.post(_flag(attempt.game_id), {"row": 0, "col": 0}, format="json")
        assert unflagged.json()["board"]["cells"][0][0] == {"revealed": False, "flagged": False}

    def test_revealed_cell_cannot_be_flagged(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 3}, format="json")
        response = alpha_client.post(_flag(attempt.game_id), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 409

    def test_invalid_coordinates(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_flag(attempt.game_id), {"row": 9, "col": 0}, format="json")
        assert response.status_code == 422

    def test_finished_attempt_rejects_flag(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_reveal(attempt.game_id), {"row": 0, "col": 4}, format="json")
        response = alpha_client.post(_flag(attempt.game_id), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 409

    def test_flag_rejected_when_contest_is_not_running(
        self, alpha, node, alpha_client, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.post(_flag(attempt.game_id), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 403
