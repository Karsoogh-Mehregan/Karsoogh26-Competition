"""The shared clock (`game/state/`) and the mentor controls (`game/settings/`)."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone

from game.models import GameSettings, GameStatus
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()

STATE_URL = "/api/game/state/"
SETTINGS_URL = "/api/game/settings/"


@pytest.fixture
def team():
    return Team.objects.create(code="alpha", name="Alpha", balance=400)


# Each role gets its own Client: they share one session cookie jar otherwise,
# so logging in as the player would silently sign the mentor out.
@pytest.fixture
def player(team):
    session = Client()
    session.force_login(User.objects.create_user("player", password="secret", team=team))
    return session


@pytest.fixture
def mentor():
    user = User.objects.create_user("mentor", password="secret")
    user.groups.add(Group.objects.get(name="Mentors"))
    session = Client()
    session.force_login(user)
    return session


def _patch(client, payload):
    return client.patch(SETTINGS_URL, payload, content_type="application/json")


# --- the shared clock --------------------------------------------------------


def test_state_is_readable_by_any_logged_in_team(player):
    response = player.get(STATE_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == GameStatus.NOT_STARTED
    assert body["is_running"] is False
    assert body["server_time"] is not None


def test_state_is_closed_to_anonymous_visitors(client):
    assert client.get(STATE_URL).status_code == 403


def test_state_carries_the_server_clock(player):
    """The whole point: clients trust this, not their own wall clock."""
    before = timezone.now()
    body = player.get(STATE_URL).json()
    after = timezone.now()

    from django.utils.dateparse import parse_datetime

    server_time = parse_datetime(body["server_time"])
    assert before <= server_time <= after


def test_no_clock_before_kick_off(player):
    body = player.get(STATE_URL).json()
    assert body["started_at"] is None
    assert body["elapsed_seconds"] is None
    assert body["remaining_seconds"] is None


def test_running_stamps_started_at_once(mentor, player):
    _patch(mentor, {"status": GameStatus.RUNNING})
    first = player.get(STATE_URL).json()["started_at"]
    assert first is not None

    _patch(mentor, {"status": GameStatus.PAUSED})
    _patch(mentor, {"status": GameStatus.RUNNING})
    assert player.get(STATE_URL).json()["started_at"] == first


def test_elapsed_counts_up_from_kick_off(player):
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.started_at = timezone.now() - timedelta(minutes=30)
    settings.save(update_fields=["status", "started_at"])

    assert player.get(STATE_URL).json()["elapsed_seconds"] == pytest.approx(1800, abs=5)


def test_remaining_counts_down_to_the_planned_finish(player):
    settings = GameSettings.load()
    settings.ends_at = timezone.now() + timedelta(minutes=10)
    settings.save(update_fields=["ends_at"])

    assert player.get(STATE_URL).json()["remaining_seconds"] == pytest.approx(600, abs=5)


def test_remaining_never_goes_negative(player):
    settings = GameSettings.load()
    settings.ends_at = timezone.now() - timedelta(minutes=5)
    settings.save(update_fields=["ends_at"])

    assert player.get(STATE_URL).json()["remaining_seconds"] == 0


# --- mentor controls ---------------------------------------------------------


def test_only_mentors_may_read_settings(player):
    assert player.get(SETTINGS_URL).status_code == 403


def test_only_mentors_may_change_settings(player):
    assert _patch(player, {"status": GameStatus.RUNNING}).status_code == 403
    assert GameSettings.load().status == GameStatus.NOT_STARTED


def test_mentor_starts_the_game(mentor):
    response = _patch(mentor, {"status": GameStatus.RUNNING})
    assert response.status_code == 200
    assert GameSettings.load().is_running is True


def test_mentor_pauses_and_finishes(mentor):
    _patch(mentor, {"status": GameStatus.RUNNING})
    _patch(mentor, {"status": GameStatus.PAUSED})
    assert GameSettings.load().is_paused is True

    _patch(mentor, {"status": GameStatus.FINISHED})
    assert GameSettings.load().status == GameStatus.FINISHED


def test_a_patch_touches_only_what_it_names(mentor):
    _patch(mentor, {"initial_balance": 400})
    _patch(mentor, {"leaderboard_public": True})

    settings = GameSettings.load()
    assert settings.initial_balance == 400
    assert settings.leaderboard_public is True
    assert settings.status == GameStatus.NOT_STARTED


def test_planned_finish_is_settable(mentor, player):
    ends_at = timezone.now() + timedelta(hours=3)
    assert _patch(mentor, {"ends_at": ends_at.isoformat()}).status_code == 200
    assert player.get(STATE_URL).json()["remaining_seconds"] == pytest.approx(10800, abs=5)


def test_planned_finish_can_be_cleared(mentor, player):
    _patch(mentor, {"ends_at": (timezone.now() + timedelta(hours=1)).isoformat()})
    assert _patch(mentor, {"ends_at": None}).status_code == 200
    assert player.get(STATE_URL).json()["remaining_seconds"] is None


def test_a_zero_answer_window_is_rejected(mentor):
    response = _patch(mentor, {"attempt_ttl_minutes": 0})
    assert response.status_code == 400
    assert GameSettings.load().attempt_ttl_minutes == 15


def test_an_unknown_status_is_rejected(mentor):
    assert _patch(mentor, {"status": "elevenses"}).status_code == 400
    assert GameSettings.load().status == GameStatus.NOT_STARTED


def test_settings_never_expose_a_writable_started_at(mentor):
    """started_at belongs to the model, so a client cannot rewrite history."""
    body = mentor.get(SETTINGS_URL).json()
    assert "started_at" not in body

    _patch(mentor, {"status": GameStatus.RUNNING})
    stamped = GameSettings.load().started_at
    _patch(mentor, {"started_at": (timezone.now() - timedelta(days=1)).isoformat()})
    assert GameSettings.load().started_at == stamped


def test_leaderboard_opens_to_teams_when_published(mentor, player):
    assert player.get("/api/leaderboard/").status_code == 403

    _patch(mentor, {"leaderboard_public": True})
    assert player.get("/api/leaderboard/").status_code == 200
