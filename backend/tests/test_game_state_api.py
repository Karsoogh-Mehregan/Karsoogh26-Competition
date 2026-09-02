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
RESTART_URL = "/api/game/restart/"


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


@pytest.fixture
def game_god():
    user = User.objects.create_user("game-god", password="secret")
    user.groups.add(Group.objects.get(name="GameGods"))
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


def test_running_stamps_started_at_once(game_god, player):
    _patch(game_god, {"status": GameStatus.RUNNING})
    first = player.get(STATE_URL).json()["started_at"]
    assert first is not None

    _patch(game_god, {"status": GameStatus.PAUSED})
    _patch(game_god, {"status": GameStatus.RUNNING})
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


def test_teams_may_not_read_settings(player):
    assert player.get(SETTINGS_URL).status_code == 403


def test_teams_may_not_change_settings(player):
    assert _patch(player, {"status": GameStatus.RUNNING}).status_code == 403
    assert GameSettings.load().status == GameStatus.NOT_STARTED


def test_a_plain_mentor_may_not_drive_the_game(mentor):
    """Grading is a mentor's job; running the event is not."""
    assert mentor.get(SETTINGS_URL).status_code == 403
    assert _patch(mentor, {"status": GameStatus.RUNNING}).status_code == 403
    assert (
        mentor.post(RESTART_URL, {"confirm": True}, content_type="application/json").status_code
        == 403
    )
    assert GameSettings.load().status == GameStatus.NOT_STARTED


def test_a_superuser_passes_as_a_game_god(client):
    """Standard Django behaviour, and the escape hatch when the group is empty."""
    client.force_login(User.objects.create_superuser("root", password="secret"))
    assert _patch(client, {"status": GameStatus.RUNNING}).status_code == 200


def test_game_god_starts_the_game(game_god):
    response = _patch(game_god, {"status": GameStatus.RUNNING})
    assert response.status_code == 200
    assert GameSettings.load().is_running is True


def test_game_god_pauses_and_finishes(game_god):
    _patch(game_god, {"status": GameStatus.RUNNING})
    _patch(game_god, {"status": GameStatus.PAUSED})
    assert GameSettings.load().is_paused is True

    _patch(game_god, {"status": GameStatus.FINISHED})
    assert GameSettings.load().status == GameStatus.FINISHED


def test_a_patch_touches_only_what_it_names(game_god):
    _patch(game_god, {"initial_balance": 400})
    _patch(game_god, {"leaderboard_public": True})

    settings = GameSettings.load()
    assert settings.initial_balance == 400
    assert settings.leaderboard_public is True
    assert settings.status == GameStatus.NOT_STARTED


def test_planned_finish_is_settable(game_god, player):
    ends_at = timezone.now() + timedelta(hours=3)
    assert _patch(game_god, {"ends_at": ends_at.isoformat()}).status_code == 200
    assert player.get(STATE_URL).json()["remaining_seconds"] == pytest.approx(10800, abs=5)


def test_planned_finish_can_be_cleared(game_god, player):
    _patch(game_god, {"ends_at": (timezone.now() + timedelta(hours=1)).isoformat()})
    assert _patch(game_god, {"ends_at": None}).status_code == 200
    assert player.get(STATE_URL).json()["remaining_seconds"] is None


def test_a_zero_answer_window_is_rejected(game_god):
    response = _patch(game_god, {"attempt_ttl_minutes": 0})
    assert response.status_code == 400
    assert GameSettings.load().attempt_ttl_minutes == 15


def test_an_unknown_status_is_rejected(game_god):
    assert _patch(game_god, {"status": "elevenses"}).status_code == 400
    assert GameSettings.load().status == GameStatus.NOT_STARTED


def test_settings_never_expose_a_writable_started_at(game_god):
    """started_at belongs to the model, so a client cannot rewrite history."""
    body = game_god.get(SETTINGS_URL).json()
    assert "started_at" not in body

    _patch(game_god, {"status": GameStatus.RUNNING})
    stamped = GameSettings.load().started_at
    _patch(game_god, {"started_at": (timezone.now() - timedelta(days=1)).isoformat()})
    assert GameSettings.load().started_at == stamped


def test_leaderboard_opens_to_teams_when_published(game_god, player):
    assert player.get("/api/leaderboard/").status_code == 403

    _patch(game_god, {"leaderboard_public": True})
    assert player.get("/api/leaderboard/").status_code == 200


# --- restart ------------------------------------------------------------------


def _restart(client, payload=None):
    return client.post(
        RESTART_URL,
        {"confirm": True} if payload is None else payload,
        content_type="application/json",
    )


@pytest.fixture
def played_board(team):
    """A team mid-game: colour, a spawn, a graded holding and a submission."""
    from game.models import LevelConfig, Node, Occupancy, Submission

    spawn = LevelConfig.objects.get(level="spawn")
    easy = LevelConfig.objects.get(level="easy")
    start = Node.objects.create(code="L1_0", name="L1_0", level=spawn)
    house = Node.objects.create(code="L1_2", name="L1_2", level=easy)

    team.color = "#d92121"
    team.draft_order = 1
    team.balance = 120
    team.save(update_fields=["color", "draft_order", "balance"])

    Occupancy.objects.create(team=team, node=start, slot=1, is_spawn=True)
    holding = Occupancy.objects.create(
        team=team,
        node=house,
        slot=1,
        question_assigned_at=timezone.now(),
    )
    Submission.objects.create(
        occupancy=holding,
        body="42",
        submitted_by=User.objects.create_user("submitter", password="secret", team=team),
    )
    return team


def test_restart_clears_the_board(game_god, played_board):
    from game.models import Occupancy, Submission

    response = _restart(game_god)
    assert response.status_code == 200
    assert response.json() == {"occupancies": 2, "submissions": 1, "teams": 1}
    assert Occupancy.objects.count() == 0
    assert Submission.objects.count() == 0


def test_restart_refunds_and_unclaims_every_team(game_god, played_board):
    _restart(game_god)

    played_board.refresh_from_db()
    assert played_board.balance == GameSettings.load().initial_balance
    assert played_board.color is None
    assert played_board.draft_order is None


def test_restart_puts_the_game_back_to_not_started(game_god):
    _patch(game_god, {"status": GameStatus.RUNNING})
    assert GameSettings.load().started_at is not None

    _restart(game_god)

    settings = GameSettings.load()
    assert settings.status == GameStatus.NOT_STARTED
    assert settings.started_at is None


def test_restart_keeps_the_planned_finish(game_god):
    """An organiser typed it in; dropping it silently is worse than a stale value."""
    ends_at = timezone.now() + timedelta(hours=2)
    _patch(game_god, {"ends_at": ends_at.isoformat()})

    _restart(game_god)
    assert GameSettings.load().ends_at is not None


def test_restart_keeps_the_map_and_the_question_bank(game_god, played_board):
    from game.models import LevelConfig, Node

    nodes = Node.objects.count()
    levels = LevelConfig.objects.count()

    _restart(game_god)

    assert Node.objects.count() == nodes
    assert LevelConfig.objects.count() == levels


def test_restart_demands_confirmation(game_god, played_board):
    from game.models import Occupancy

    assert _restart(game_god, {"confirm": False}).status_code == 400
    assert _restart(game_god, {}).status_code == 400
    assert Occupancy.objects.count() == 2


def test_restart_is_closed_to_teams(player, played_board):
    from game.models import Occupancy

    assert _restart(player).status_code == 403
    assert Occupancy.objects.count() == 2


def test_restart_is_idempotent_on_an_empty_board(game_god):
    assert _restart(game_god).status_code == 200
    second = _restart(game_god)
    assert second.status_code == 200
    assert second.json()["occupancies"] == 0
