"""Session-cookie auth and the shared game-status permission."""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache

from accounts.permissions import GameIsRunning
from game.models import GameSettings, GameStatus
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()


@pytest.fixture
def user():
    user = User.objects.create_user("mentor", password="secret")
    user.groups.add(Group.objects.get(name="Mentors"))
    return user


@pytest.fixture
def team():
    return Team.objects.create(code="alpha", name="Alpha", balance=42)


@pytest.fixture
def other_team():
    return Team.objects.create(code="beta", name="Beta", balance=7)


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


def test_login_returns_me_shape(client, user):
    response = client.post(
        "/api/auth/login/",
        {"username": "mentor", "password": "secret"},
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": user.pk,
        "username": "mentor",
        "is_staff": False,
        "is_mentor": True,
        "is_game_god": False,
        "is_announcer": False,
        "is_designer": False,
        "is_duel_mentor": False,
        "team": None,
    }


def test_login_rejects_bad_password(client, user):
    response = client.post(
        "/api/auth/login/",
        {"username": "mentor", "password": "wrong"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "_auth_user_id" not in client.session


def test_csrf_sets_cookie(client):
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 200
    assert "csrftoken" in response.cookies
    assert response.json()["csrf_token"]


def test_logout_flushes_session(auth_client):
    assert auth_client.post("/api/auth/logout/").status_code == 204
    assert auth_client.get("/api/auth/me/").status_code == 403


def test_me_returns_mentor_identity(auth_client, user):
    response = auth_client.get("/api/auth/me/")
    assert response.status_code == 200
    assert response.json() == {
        "id": user.pk,
        "username": "mentor",
        "is_staff": False,
        "is_mentor": True,
        "is_game_god": False,
        "is_announcer": False,
        "is_designer": False,
        "is_duel_mentor": False,
        "team": None,
    }


def test_me_returns_team_identity_for_a_team_account(client, team):
    user = User.objects.create_user("user-alpha", password="secret", team=team)
    client.force_login(user)

    response = client.get("/api/auth/me/")
    assert response.status_code == 200
    body = response.json()
    assert body["is_mentor"] is False
    assert body["team"] == {"code": team.code, "name": team.name}


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/api/auth/me/", None),
        ("get", "/api/teams/", None),
        ("post", "/api/teams/alpha/claim-start/", {"node": "L1_0"}),
    ],
)
def test_anonymous_requests_are_403(client, method, path, payload):
    extra = {"content_type": "application/json"} if payload is not None else {}
    response = getattr(client, method)(path, payload or {}, **extra)
    assert response.status_code == 403


def test_teams_list_returns_code_name_balance(auth_client, team, other_team):
    response = auth_client.get("/api/teams/")
    assert response.status_code == 200
    assert response.json() == [
        {
            "code": "alpha",
            "name": "Alpha",
            "balance": 42,
            "holdings": [],
            "color": None,
            "cleared_tolls": [],
            "active_tolls": [],
        },
        {
            "code": "beta",
            "name": "Beta",
            "balance": 7,
            "holdings": [],
            "color": None,
            "cleared_tolls": [],
            "active_tolls": [],
        },
    ]


def test_teams_list_hides_other_teams_balance_from_a_team_account(client, team, other_team):
    user = User.objects.create_user("user-alpha", password="secret", team=team)
    client.force_login(user)

    response = client.get("/api/teams/")
    assert response.status_code == 200
    by_code = {row["code"]: row["balance"] for row in response.json()}
    assert by_code == {"alpha": 42, "beta": None}


def test_game_is_running_permission():
    settings = GameSettings.load()
    assert settings.status == GameStatus.NOT_STARTED
    assert GameIsRunning().has_permission(SimpleNamespace(), None) is False

    settings.status = GameStatus.RUNNING
    settings.save()
    assert GameIsRunning().has_permission(SimpleNamespace(), None) is True


def test_login_throttled_after_ten_attempts(client, user):
    payload = {"username": "mentor", "password": "wrong"}
    for _ in range(10):
        assert (
            client.post("/api/auth/login/", payload, content_type="application/json").status_code
            == 400
        )
    assert (
        client.post("/api/auth/login/", payload, content_type="application/json").status_code == 429
    )
