"""HTTP layer over Minesweeper services — auth, attempt isolation, sanitization."""

import copy
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework.test import APIClient

from game.models import Edge, GameSettings, GameStatus, LevelConfig, Node, Occupancy
from minesweeper.models import (
    DIFFICULTY_LAYOUTS,
    MinesweeperAttempt,
    MinesweeperDifficulty,
    MinesweeperGame,
    MinesweeperSettings,
    MinesweeperStatus,
)
from minesweeper.services import create_attempt, create_game, reveal_cell
from teams.models import Team

pytestmark = pytest.mark.django_db
User = get_user_model()

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


def _enter(node_code):
    return f"/api/minesweeper/nodes/{node_code}/enter/"


def _start(node_code):
    return f"/api/minesweeper/nodes/{node_code}/start/"


def _detail(pk):
    return f"/api/minesweeper/attempts/{pk}/"


def _reveal(pk):
    return f"/api/minesweeper/attempts/{pk}/reveal/"


def _flag(pk):
    return f"/api/minesweeper/attempts/{pk}/flag/"


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
def other_node():
    return Node.objects.create(
        code="ms2",
        name="MS 2",
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


def _begin(client, node):
    entered = client.post(_enter(node.code), {}, format="json")
    assert entered.status_code == 200, entered.content
    token = entered.json()["entry"]
    return client.post(_start(node.code), {"entry": token}, format="json")


def _undirected(a: Node, b: Node) -> Edge:
    lower, upper = sorted((a, b), key=lambda node: node.pk)
    return Edge.objects.create(a=lower, b=upper, directed=False)


def grant_access(team: Team, node: Node) -> Occupancy:
    spawn = LevelConfig.objects.get(level="spawn")
    home = Node.objects.create(
        code=f"ms-home-{team.pk}-{node.pk}",
        name="home",
        level=spawn,
    )
    holding = Occupancy.objects.create(team=team, node=home, slot=1, is_spawn=True)
    _undirected(home, node)
    return holding


@pytest.fixture(autouse=True)
def _reachable_play_nodes(alpha, beta, node, other_node):
    home_a = grant_access(alpha, node)
    home_b = grant_access(beta, node)
    _undirected(home_a.node, other_node)
    _undirected(home_b.node, other_node)


def _configure(node, difficulty=MinesweeperDifficulty.HARD, *, enabled=True):
    return MinesweeperSettings.objects.create(
        node=node,
        difficulty=difficulty,
        enabled=enabled,
    )


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


def _attempt(team, node, difficulty=MinesweeperDifficulty.EASY):
    game = create_game(node, difficulty)
    return create_attempt(game, team)


def _split_attempt(team, node):
    game = create_game(node, MinesweeperDifficulty.EASY)
    _install_layout(game, SPLIT_MINES)
    return create_attempt(game, team)


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


def _assert_finished_layout(board, *, mine_count: int):
    mines = 0
    for row in board["cells"]:
        for cell in row:
            assert set(cell) == {"revealed", "flagged", "adjacent_mines", "mine"}
            if cell["mine"]:
                mines += 1
    assert mines == mine_count


class TestAuthentication:
    @pytest.mark.parametrize(
        "method,url_builder,payload",
        [
            ("post", lambda node: _enter(node.code), None),
            ("post", lambda node: _start(node.code), {"entry": "x"}),
            ("get", lambda _node: _detail(1), None),
            ("post", lambda _node: _reveal(1), {"row": 0, "col": 0}),
            ("post", lambda _node: _flag(1), {"row": 0, "col": 0}),
        ],
    )
    def test_anonymous_is_rejected(self, running_contest, node, method, url_builder, payload):
        client = APIClient()
        kwargs = {"format": "json"} if payload is not None else {}
        response = getattr(client, method)(url_builder(node), payload or {}, **kwargs)
        assert response.status_code == 403

    def test_user_without_a_team_cannot_enter(self, running_contest, node):
        _configure(node)
        user = User.objects.create_user("lone", password="pw")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(_enter(node.code), {}, format="json")
        assert response.status_code == 403

    def test_mentor_cannot_enter(self, running_contest, mentor, node):
        _configure(node)
        client = APIClient()
        client.force_authenticate(user=mentor)
        response = client.post(_enter(node.code), {}, format="json")
        assert response.status_code == 403
        assert not mentor.team_id


class TestEntryAuthorization:
    def test_player_can_enter_an_enabled_node(self, alpha_client, node, running_contest):
        _configure(node)
        response = alpha_client.post(_enter(node.code), {}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["node"] == node.code
        assert body["entry"]

    def test_missing_settings_are_rejected(self, alpha_client, node, running_contest):
        response = alpha_client.post(_enter(node.code), {}, format="json")
        assert response.status_code == 404
        assert response.json() == {"detail": "بازی پیدا نشد."}

    def test_disabled_settings_are_conflict(self, alpha_client, node, running_contest):
        _configure(node, enabled=False)
        response = alpha_client.post(_enter(node.code), {}, format="json")
        assert response.status_code == 409
        assert response.json() == {"detail": "این بازی مین‌روب فعال نیست."}

    def test_invalid_node_code_is_404(self, alpha_client, running_contest):
        response = alpha_client.post(_enter("no-such-node"), {}, format="json")
        assert response.status_code == 404
        assert response.json() == {"detail": "بازی پیدا نشد."}

    def test_entry_for_node_a_cannot_start_node_b(
        self, alpha_client, node, other_node, running_contest
    ):
        _configure(node)
        _configure(other_node)
        entered = alpha_client.post(_enter(node.code), {}, format="json")
        token = entered.json()["entry"]
        response = alpha_client.post(_start(other_node.code), {"entry": token}, format="json")
        assert response.status_code == 403
        assert response.json() == {"detail": "اجازهٔ ورود به این بازی صادر نشده است."}
        assert MinesweeperGame.objects.count() == 0

    def test_entry_cannot_be_reused(self, alpha_client, node, running_contest):
        _configure(node)
        first = _begin(alpha_client, node)
        assert first.status_code == 201
        entered = alpha_client.post(_enter(node.code), {}, format="json")
        token = entered.json()["entry"]
        second = alpha_client.post(_start(node.code), {"entry": token}, format="json")
        assert second.status_code == 201
        third = alpha_client.post(_start(node.code), {"entry": token}, format="json")
        assert third.status_code == 403
        assert MinesweeperGame.objects.filter(node=node).count() == 1

    def test_expired_entry_is_rejected(self, alpha_client, node, running_contest, monkeypatch):
        _configure(node)
        started = timezone.now()
        monkeypatch.setattr("minesweeper.services._now", lambda: started)
        entered = alpha_client.post(_enter(node.code), {}, format="json")
        token = entered.json()["entry"]
        monkeypatch.setattr("minesweeper.services._now", lambda: started + timedelta(seconds=61))
        response = alpha_client.post(_start(node.code), {"entry": token}, format="json")
        assert response.status_code == 403
        assert MinesweeperGame.objects.count() == 0

    def test_start_without_entry_is_rejected(self, alpha_client, node, running_contest):
        _configure(node)
        response = alpha_client.post(_start(node.code), {}, format="json")
        assert response.status_code == 400
        assert MinesweeperGame.objects.count() == 0

    def test_start_with_forged_entry_is_rejected(self, alpha_client, node, running_contest):
        _configure(node)
        response = alpha_client.post(_start(node.code), {"entry": "forged"}, format="json")
        assert response.status_code == 403
        assert response.json() == {"detail": "اجازهٔ ورود به این بازی صادر نشده است."}
        assert MinesweeperGame.objects.count() == 0

    def test_other_session_cannot_use_this_entry(
        self, alpha_client, beta_client, node, running_contest
    ):
        _configure(node)
        entered = alpha_client.post(_enter(node.code), {}, format="json")
        token = entered.json()["entry"]
        response = beta_client.post(_start(node.code), {"entry": token}, format="json")
        assert response.status_code == 403
        assert response.json() == {"detail": "اجازهٔ ورود به این بازی صادر نشده است."}
        assert MinesweeperGame.objects.count() == 0

    def test_graph_node_code_is_accepted(self, alpha_client, alpha, running_contest):
        node = Node.objects.create(
            code="C34_0",
            name="Connector",
            level=LevelConfig.objects.get(level="toll"),
        )
        grant_access(alpha, node)
        _configure(node)
        response = alpha_client.post(_enter("C34_0"), {}, format="json")
        assert response.status_code == 200
        assert response.json()["node"] == "C34_0"


class TestStartPlay:
    def test_creates_a_game_and_attempt_for_the_authenticated_team(
        self, alpha_client, alpha, node, running_contest
    ):
        layout = DIFFICULTY_LAYOUTS[MinesweeperDifficulty.HARD]
        _configure(node, MinesweeperDifficulty.HARD)
        response = _begin(alpha_client, node)
        assert response.status_code == 201
        body = response.json()
        assert body["node"] == node.code
        assert body["difficulty"] == MinesweeperDifficulty.HARD
        assert body["width"] == layout["width"]
        assert body["height"] == layout["height"]
        assert body["mine_count"] == layout["mine_count"]
        assert body["status"] == MinesweeperStatus.IN_PROGRESS
        assert "team" not in body
        assert "id" not in body
        assert body["game_id"]
        assert body["attempt_id"]
        _assert_no_hidden_mines(body["board"])
        attempt = MinesweeperAttempt.objects.get(pk=body["attempt_id"])
        assert attempt.team_id == alpha.pk
        assert attempt.game_id == body["game_id"]
        assert attempt.game.node_id == node.pk

    def test_client_does_not_choose_difficulty(self, alpha_client, node, running_contest):
        _configure(node, MinesweeperDifficulty.MEDIUM)
        response = _begin(alpha_client, node)
        assert response.status_code == 201
        assert response.json()["difficulty"] == MinesweeperDifficulty.MEDIUM

    def test_same_team_refresh_resumes_the_active_attempt(
        self, alpha_client, alpha, node, running_contest
    ):
        _configure(node, MinesweeperDifficulty.EASY)
        first = _begin(alpha_client, node)
        second = _begin(alpha_client, node)
        assert first.status_code == 201
        assert second.status_code == 201
        assert second.json()["game_id"] == first.json()["game_id"]
        assert second.json()["attempt_id"] == first.json()["attempt_id"]
        assert MinesweeperGame.objects.filter(node=node).count() == 1
        assert MinesweeperAttempt.objects.filter(team=alpha).count() == 1

    def test_lost_attempt_starts_a_new_game(self, alpha_client, alpha, node, running_contest):
        _configure(node, MinesweeperDifficulty.EASY)
        first = _begin(alpha_client, node)
        assert first.status_code == 201
        attempt = MinesweeperAttempt.objects.get(pk=first.json()["attempt_id"])
        attempt.status = MinesweeperStatus.LOST
        attempt.finished_at = timezone.now()
        attempt.save(update_fields=["status", "finished_at"])

        second = _begin(alpha_client, node)
        assert second.status_code == 201
        assert second.json()["game_id"] != first.json()["game_id"]
        assert second.json()["attempt_id"] != first.json()["attempt_id"]
        assert second.json()["status"] == MinesweeperStatus.IN_PROGRESS
        assert MinesweeperGame.objects.filter(node=node).count() == 2
        assert MinesweeperAttempt.objects.filter(team=alpha).count() == 2

    def test_won_attempt_is_returned_instead_of_a_fresh_board(
        self, alpha_client, alpha, node, running_contest
    ):
        _configure(node, MinesweeperDifficulty.EASY)
        first = _begin(alpha_client, node)
        assert first.status_code == 201
        attempt = MinesweeperAttempt.objects.get(pk=first.json()["attempt_id"])
        attempt.status = MinesweeperStatus.WON
        attempt.finished_at = timezone.now()
        attempt.save(update_fields=["status", "finished_at"])

        second = _begin(alpha_client, node)
        assert second.status_code == 201
        assert second.json()["attempt_id"] == first.json()["attempt_id"]
        assert second.json()["status"] == MinesweeperStatus.WON
        assert MinesweeperGame.objects.filter(node=node).count() == 1
        assert MinesweeperAttempt.objects.filter(team=alpha).count() == 1

    def test_two_teams_get_independent_games(
        self, alpha_client, beta_client, alpha, beta, node, running_contest
    ):
        _configure(node, MinesweeperDifficulty.HARD)
        first = _begin(alpha_client, node)
        second = _begin(beta_client, node)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["game_id"] != second.json()["game_id"]
        assert first.json()["attempt_id"] != second.json()["attempt_id"]
        assert MinesweeperAttempt.objects.get(pk=first.json()["attempt_id"]).team_id == alpha.pk
        assert MinesweeperAttempt.objects.get(pk=second.json()["attempt_id"]).team_id == beta.pk

    def test_missing_node_is_404(self, alpha_client, running_contest):
        response = alpha_client.post(_enter("no-such-node"), {}, format="json")
        assert response.status_code == 404
        assert response.json() == {"detail": "بازی پیدا نشد."}

    def test_enter_rejected_when_contest_is_not_running(self, alpha_client, node, running_contest):
        _configure(node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.post(_enter(node.code), {}, format="json")
        assert response.status_code == 403
        assert not MinesweeperGame.objects.filter(node=node).exists()

    def test_start_then_reveal(self, alpha_client, alpha, node, running_contest):
        _configure(node, MinesweeperDifficulty.EASY)
        started = _begin(alpha_client, node)
        assert started.status_code == 201
        attempt = MinesweeperAttempt.objects.get(pk=started.json()["attempt_id"])
        _install_layout(attempt.game, SPLIT_MINES)
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        cell = response.json()["board"]["cells"][0][3]
        assert cell["revealed"] is True
        _assert_no_hidden_mines(response.json()["board"])
        attempt.refresh_from_db()
        assert attempt.board["cells"][0][3]["revealed"] is True


class TestAttemptDetail:
    def test_owner_can_read_sanitized_board(
        self, alpha, node, alpha_client, running_contest, monkeypatch
    ):
        def first_k(population, k):
            return population[:k]

        monkeypatch.setattr("minesweeper.services.random.sample", first_k)
        attempt = _attempt(alpha, node)

        response = alpha_client.get(_detail(attempt.pk))
        assert response.status_code == 200
        body = response.json()
        assert body["game_id"] == attempt.game_id
        assert body["attempt_id"] == attempt.pk
        assert body["node"] == node.code
        _assert_no_hidden_mines(body["board"])
        assert body["board"]["cells"][0][0] == {"revealed": False, "flagged": False}
        assert body["board"]["cells"][8][8] == {"revealed": False, "flagged": False}

    def test_in_progress_detail_does_not_expose_mines(
        self, alpha, node, alpha_client, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.get(_detail(attempt.pk))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.IN_PROGRESS
        assert body["score"] == 0
        _assert_no_hidden_mines(body["board"])

    def test_missing_attempt_is_404(self, alpha_client, running_contest):
        response = alpha_client.get(_detail(999_999))
        assert response.status_code == 404
        assert response.json() == {"detail": "بازی پیدا نشد."}

    def test_other_team_cannot_read_this_attempt(
        self, alpha, node, alpha_client, beta_client, running_contest
    ):
        attempt = _attempt(alpha, node)
        response = beta_client.get(_detail(attempt.pk))
        assert response.status_code == 404
        assert response.json() == alpha_client.get(_detail(999_999)).json()

    def test_revealed_cell_exposes_adjacent_not_mine(
        self, alpha, node, alpha_client, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        reveal_cell(attempt.pk, 0, 3)
        response = alpha_client.get(_detail(attempt.pk))
        assert response.status_code == 200
        cell = response.json()["board"]["cells"][0][3]
        assert cell["revealed"] is True
        assert "adjacent_mines" in cell
        assert "mine" not in cell
        _assert_no_hidden_mines(response.json()["board"])

    def test_finished_attempt_exposes_mines(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        reveal_cell(attempt.pk, 0, 4)
        response = alpha_client.get(_detail(attempt.pk))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.LOST
        assert body["score"] == 0
        _assert_finished_layout(body["board"], mine_count=attempt.game.mine_count)
        mine = body["board"]["cells"][0][4]
        assert mine["mine"] is True
        assert mine["revealed"] is True
        hidden_mine = body["board"]["cells"][8][8]
        assert hidden_mine["mine"] is True
        assert hidden_mine["revealed"] is False

    def test_won_attempt_exposes_mines(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        _reveal_all_safe_except(attempt, {(0, 3)})
        reveal_cell(attempt.pk, 0, 3)
        response = alpha_client.get(_detail(attempt.pk))
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.WON
        assert body["score"] > 0
        _assert_finished_layout(body["board"], mine_count=attempt.game.mine_count)
        assert body["board"]["cells"][0][4]["mine"] is True

    def test_get_allowed_when_contest_is_not_running(
        self, alpha, node, alpha_client, running_contest
    ):
        attempt = _attempt(alpha, node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.get(_detail(attempt.pk))
        assert response.status_code == 200


class TestTeamIsolation:
    def test_other_team_cannot_reveal_or_flag(self, alpha, node, beta_client, running_contest):
        attempt = _split_attempt(alpha, node)
        assert (
            beta_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json").status_code
            == 404
        )
        assert (
            beta_client.post(_flag(attempt.pk), {"row": 0, "col": 0}, format="json").status_code
            == 404
        )
        attempt.refresh_from_db()
        assert attempt.board["cells"][0][3]["revealed"] is False
        assert attempt.board["cells"][0][0]["flagged"] is False

    def test_reveal_does_not_create_an_attempt_for_another_team(
        self, alpha, beta, node, alpha_client, beta_client, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        assert response.json()["board"]["cells"][0][3]["revealed"] is True

        assert beta_client.get(_detail(attempt.pk)).status_code == 404
        assert MinesweeperAttempt.objects.filter(game=attempt.game, team=beta).count() == 0
        alpha_attempt = MinesweeperAttempt.objects.get(pk=attempt.pk)
        assert alpha_attempt.board["cells"][0][3]["revealed"] is True

    def test_progress_of_one_attempt_does_not_affect_another(
        self, alpha_client, beta_client, node, running_contest
    ):
        _configure(node, MinesweeperDifficulty.EASY)
        alpha_started = _begin(alpha_client, node)
        beta_started = _begin(beta_client, node)
        alpha_id = alpha_started.json()["attempt_id"]
        beta_id = beta_started.json()["attempt_id"]
        alpha_attempt = MinesweeperAttempt.objects.get(pk=alpha_id)
        _install_layout(alpha_attempt.game, SPLIT_MINES)

        response = alpha_client.post(_reveal(alpha_id), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        assert response.json()["board"]["cells"][0][3]["revealed"] is True

        beta_board = beta_client.get(_detail(beta_id)).json()["board"]
        assert beta_board["cells"][0][3]["revealed"] is False
        _assert_no_hidden_mines(beta_board)


class TestRevealApi:
    def test_safe_reveal(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json")
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
        response = alpha_client.post(_reveal(attempt.pk), {"row": -1, "col": 0}, format="json")
        assert response.status_code == 422

    def test_already_revealed(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json")
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 409

    def test_flagged_cell(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_flag(attempt.pk), {"row": 0, "col": 0}, format="json")
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 409

    def test_mine_causes_loss(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 4}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.LOST
        assert body["score"] == 0
        assert body["finished_at"] is not None
        _assert_finished_layout(body["board"], mine_count=attempt.game.mine_count)
        assert body["board"]["cells"][0][4]["mine"] is True

    def test_win_after_final_safe_cell(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        _reveal_all_safe_except(attempt, {(0, 3)})
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == MinesweeperStatus.WON
        assert body["score"] > 0
        assert body["finished_at"] is not None
        _assert_finished_layout(body["board"], mine_count=attempt.game.mine_count)
        assert body["board"]["cells"][0][4]["mine"] is True

    def test_flood_fill_response(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 200
        cells = response.json()["board"]["cells"]
        assert cells[0][0]["revealed"] is True
        assert cells[2][2]["revealed"] is True
        assert cells[0][5]["revealed"] is False
        assert response.json()["status"] == MinesweeperStatus.IN_PROGRESS
        _assert_no_hidden_mines(response.json()["board"])

    def test_finished_attempt_rejects_reveal(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 4}, format="json")
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 409

    def test_reveal_rejected_when_contest_is_not_running(
        self, alpha, node, alpha_client, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 403


class TestFlagApi:
    def test_flag_and_unflag(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        flagged = alpha_client.post(_flag(attempt.pk), {"row": 0, "col": 0}, format="json")
        assert flagged.status_code == 200
        cell = flagged.json()["board"]["cells"][0][0]
        assert cell == {"revealed": False, "flagged": True}
        assert flagged.json()["status"] == MinesweeperStatus.IN_PROGRESS
        assert flagged.json()["score"] == 0

        unflagged = alpha_client.post(_flag(attempt.pk), {"row": 0, "col": 0}, format="json")
        assert unflagged.json()["board"]["cells"][0][0] == {"revealed": False, "flagged": False}

    def test_revealed_cell_cannot_be_flagged(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 3}, format="json")
        response = alpha_client.post(_flag(attempt.pk), {"row": 0, "col": 3}, format="json")
        assert response.status_code == 409

    def test_invalid_coordinates(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        response = alpha_client.post(_flag(attempt.pk), {"row": 9, "col": 0}, format="json")
        assert response.status_code == 422

    def test_finished_attempt_rejects_flag(self, alpha, node, alpha_client, running_contest):
        attempt = _split_attempt(alpha, node)
        alpha_client.post(_reveal(attempt.pk), {"row": 0, "col": 4}, format="json")
        response = alpha_client.post(_flag(attempt.pk), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 409

    def test_flag_rejected_when_contest_is_not_running(
        self, alpha, node, alpha_client, running_contest
    ):
        attempt = _split_attempt(alpha, node)
        running_contest.status = GameStatus.NOT_STARTED
        running_contest.save(update_fields=["status"])
        response = alpha_client.post(_flag(attempt.pk), {"row": 0, "col": 0}, format="json")
        assert response.status_code == 403
