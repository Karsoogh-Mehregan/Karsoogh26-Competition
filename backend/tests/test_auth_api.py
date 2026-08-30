"""Session-cookie auth, acting-as-team, and the shared game-status permission."""

from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache

from accounts.acting import ACTING_TEAM_SESSION_KEY, NoActingTeam, resolve_acting_team
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
        "acting_team": None,
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


def test_act_as_survives_across_requests(auth_client, team):
    response = auth_client.post(
        "/api/auth/act-as/",
        {"team": team.code},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["acting_team"]["code"] == "alpha"

    me = auth_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["acting_team"] == {
        "code": "alpha",
        "name": "Alpha",
        "balance": 42,
        "holdings": [],
    }


def test_act_as_null_clears_selection(auth_client, team):
    auth_client.post(
        "/api/auth/act-as/",
        {"team": team.code},
        content_type="application/json",
    )
    response = auth_client.post(
        "/api/auth/act-as/",
        {"team": None},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["acting_team"] is None
    assert auth_client.session[ACTING_TEAM_SESSION_KEY] is None
    me = auth_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["acting_team"] is None


def test_act_as_null_does_not_fall_back_to_user_team(auth_client, user, team):
    user.team = team
    user.save()
    auth_client.post(
        "/api/auth/act-as/",
        {"team": team.code},
        content_type="application/json",
    )
    response = auth_client.post(
        "/api/auth/act-as/",
        {"team": None},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["acting_team"] is None


def test_act_as_unknown_code_is_400(auth_client):
    response = auth_client.post(
        "/api/auth/act-as/",
        {"team": "nope"},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_non_staff_mentor_can_act_as_any_team(auth_client, user, other_team):
    assert user.is_staff is False
    response = auth_client.post(
        "/api/auth/act-as/",
        {"team": other_team.code},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert auth_client.session[ACTING_TEAM_SESSION_KEY] == other_team.pk


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/api/auth/me/", None),
        ("post", "/api/auth/act-as/", {"team": "alpha"}),
        ("get", "/api/teams/", None),
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
        {"code": "alpha", "name": "Alpha", "balance": 42, "holdings": []},
        {"code": "beta", "name": "Beta", "balance": 7, "holdings": []},
    ]


def test_resolve_acting_team_falls_back_to_user_team(user, team):
    user.team = team
    request = SimpleNamespace(session={}, user=user)
    assert resolve_acting_team(request) == team


def test_resolve_acting_team_raises_when_unset(user):
    request = SimpleNamespace(session={}, user=user)
    with pytest.raises(NoActingTeam):
        resolve_acting_team(request)


def test_resolve_acting_team_explicit_none_skips_user_team(user, team):
    user.team = team
    request = SimpleNamespace(session={ACTING_TEAM_SESSION_KEY: None}, user=user)
    with pytest.raises(NoActingTeam):
        resolve_acting_team(request)


def test_resolve_acting_team_clears_stale_id(user):
    request = SimpleNamespace(session={ACTING_TEAM_SESSION_KEY: 999999}, user=user)
    with pytest.raises(NoActingTeam):
        resolve_acting_team(request)
    assert ACTING_TEAM_SESSION_KEY not in request.session


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
