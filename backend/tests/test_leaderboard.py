"""GET /api/leaderboard/ — live ranks, or a freeze snapshot for competing teams."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from core.boards import Board
from game.models import GameSettings
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()

LIVE_ORDER = [
    {"rank": 1, "code": "bravo", "name": "Bravo", "balance": 300},
    {"rank": 2, "code": "charlie", "name": "Charlie", "balance": 200},
    {"rank": 3, "code": "alpha", "name": "Alpha", "balance": 100},
]


@pytest.fixture
def teams():
    Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=100)
    Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo", balance=300)
    Team.objects.create(board=Board.GIRLS, code="charlie", name="Charlie", balance=200)


@pytest.fixture
def client_team(teams):
    user = User.objects.create_user("user-alpha", password="x", team=Team.objects.get(code="alpha"))
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def client_mentor():
    mentor = User.objects.create_user("mentor", password="x")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    client = APIClient()
    client.force_authenticate(mentor)
    return client


def _freeze():
    settings = GameSettings.load()
    settings.leaderboard_frozen = True
    settings.save(update_fields=["leaderboard_frozen"])


def test_visible_to_a_team_by_default(client_team):
    response = client_team.get("/api/leaderboard/")
    assert response.status_code == 200
    assert response.json() == LIVE_ORDER


def test_always_visible_to_a_mentor(client_mentor, teams):
    assert client_mentor.get("/api/leaderboard/").status_code == 200
    assert client_mentor.get("/api/leaderboard/").json() == LIVE_ORDER


def test_anonymous_is_403(teams):
    assert APIClient().get("/api/leaderboard/").status_code == 403


def test_a_restart_refreshes_the_frozen_snapshot(teams, client_team):
    _freeze()
    Team.objects.filter(code="bravo").update(balance=1)

    from game.services import restart_game

    restart_game()

    rows = client_team.get("/api/leaderboard/").json()
    assert GameSettings.load().leaderboard_frozen is True
    assert {row["balance"] for row in rows} == {GameSettings.load().initial_balance}


def test_a_frozen_board_stays_put_for_a_team(client_team, client_mentor):
    _freeze()
    Team.objects.filter(code="bravo").update(balance=1)

    assert client_team.get("/api/leaderboard/").json() == LIVE_ORDER
    assert client_mentor.get("/api/leaderboard/").json() == [
        {"rank": 1, "code": "charlie", "name": "Charlie", "balance": 200},
        {"rank": 2, "code": "alpha", "name": "Alpha", "balance": 100},
        {"rank": 3, "code": "bravo", "name": "Bravo", "balance": 1},
    ]


def test_unfreezing_returns_live_ranks_to_a_team(client_team):
    _freeze()
    Team.objects.filter(code="bravo").update(balance=1)

    settings = GameSettings.load()
    settings.leaderboard_frozen = False
    settings.save(update_fields=["leaderboard_frozen"])

    assert client_team.get("/api/leaderboard/").json()[0]["code"] == "charlie"
    assert GameSettings.load().leaderboard_snapshot is None


def test_freeze_is_per_board(django_user_model, client_mentor):
    girls = Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=100)
    boys = Team.objects.create(board=Board.BOYS, code="bravo", name="Bravo", balance=10_000)
    _freeze()
    Team.objects.filter(pk=boys.pk).update(balance=1)

    user = django_user_model.objects.create_user("girl", password="x", team=girls)
    client = APIClient()
    client.force_authenticate(user)

    assert [(row["rank"], row["code"]) for row in client.get("/api/leaderboard/").json()] == [
        (1, "alpha")
    ]
    live_boys = client_mentor.get("/api/leaderboard/?board=boys").json()
    assert live_boys == [{"rank": 1, "code": "bravo", "name": "Bravo", "balance": 1}]
