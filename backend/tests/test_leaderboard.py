"""GET /api/leaderboard/ — admin-only now; freeze snapshot for a viewer with a team.

The standings are an operator-only view: teams, mentors and every other event
role get 403, only Django staff/superusers may read them. The freeze machinery
still works for an admin who also carries a team (see `sees_frozen_snapshot`),
which is the only way to reach the snapshot path through the endpoint now.
"""

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


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def client_admin(teams):
    """Staff, no team — the ordinary operator view, always live."""
    return _client(User.objects.create_user("boss", password="x", is_staff=True))


@pytest.fixture
def client_admin_team(teams):
    """Staff *and* on a team — the only viewer the freeze snapshot still reaches."""
    admin = User.objects.create_user(
        "boss-alpha", password="x", is_staff=True, team=Team.objects.get(code="alpha")
    )
    return _client(admin)


@pytest.fixture
def client_team(teams):
    user = User.objects.create_user("user-alpha", password="x", team=Team.objects.get(code="alpha"))
    return _client(user)


@pytest.fixture
def client_mentor():
    mentor = User.objects.create_user("mentor", password="x")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    return _client(mentor)


def _freeze():
    settings = GameSettings.load()
    settings.leaderboard_frozen = True
    settings.save(update_fields=["leaderboard_frozen"])


def test_visible_to_an_admin(client_admin):
    response = client_admin.get("/api/leaderboard/")
    assert response.status_code == 200
    assert response.json() == LIVE_ORDER


def test_hidden_from_a_team(client_team):
    assert client_team.get("/api/leaderboard/").status_code == 403


def test_hidden_from_a_mentor(client_mentor, teams):
    assert client_mentor.get("/api/leaderboard/").status_code == 403


def test_anonymous_is_403(teams):
    assert APIClient().get("/api/leaderboard/").status_code == 403


def test_a_restart_refreshes_the_frozen_snapshot(teams, client_admin_team):
    _freeze()
    Team.objects.filter(code="bravo").update(balance=1)

    from game.services import restart_game

    restart_game()

    rows = client_admin_team.get("/api/leaderboard/").json()
    assert GameSettings.load().leaderboard_frozen is True
    assert {row["balance"] for row in rows} == {GameSettings.load().initial_balance}


def test_a_frozen_board_stays_put_for_a_teamed_viewer(client_admin_team, client_admin):
    _freeze()
    Team.objects.filter(code="bravo").update(balance=1)

    # The teamed admin sees the frozen snapshot; the plain admin sees live.
    assert client_admin_team.get("/api/leaderboard/").json() == LIVE_ORDER
    assert client_admin.get("/api/leaderboard/").json() == [
        {"rank": 1, "code": "charlie", "name": "Charlie", "balance": 200},
        {"rank": 2, "code": "alpha", "name": "Alpha", "balance": 100},
        {"rank": 3, "code": "bravo", "name": "Bravo", "balance": 1},
    ]


def test_unfreezing_returns_live_ranks(client_admin_team):
    _freeze()
    Team.objects.filter(code="bravo").update(balance=1)

    settings = GameSettings.load()
    settings.leaderboard_frozen = False
    settings.save(update_fields=["leaderboard_frozen"])

    assert client_admin_team.get("/api/leaderboard/").json()[0]["code"] == "charlie"
    assert GameSettings.load().leaderboard_snapshot is None


def test_freeze_is_per_board():
    girls = Team.objects.create(board=Board.GIRLS, code="g1", name="G1", balance=100)
    boys = Team.objects.create(board=Board.BOYS, code="b1", name="B1", balance=10_000)
    _freeze()
    Team.objects.filter(pk=boys.pk).update(balance=1)

    # An admin on the girls board sees that board's frozen snapshot…
    girl_admin = _client(
        User.objects.create_user("girl-admin", password="x", is_staff=True, team=girls)
    )
    assert [(row["rank"], row["code"]) for row in girl_admin.get("/api/leaderboard/").json()] == [
        (1, "g1")
    ]
    # …while a plain admin reads the boys board live.
    plain_admin = _client(User.objects.create_user("boss", password="x", is_staff=True))
    live_boys = plain_admin.get("/api/leaderboard/?board=boys").json()
    assert live_boys == [{"rank": 1, "code": "b1", "name": "B1", "balance": 1}]
