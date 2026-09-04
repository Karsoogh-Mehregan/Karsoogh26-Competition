"""The shared clock (`game/state/`) and the mentor controls (`game/settings/`)."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.utils import timezone

from core.boards import Board
from game.models import GameSettings, GameStatus
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()

STATE_URL = "/api/game/state/"
SETTINGS_URL = "/api/game/settings/"
RESTART_URL = "/api/game/restart/"


@pytest.fixture
def team():
    return Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=400)


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


def test_before_kick_off_nothing_has_elapsed(player):
    """The countdown already shows the full allowance; only elapsed is absent."""
    body = player.get(STATE_URL).json()
    assert body["started_at"] is None
    assert body["elapsed_seconds"] is None
    assert body["accumulated_seconds"] == 0
    assert body["running_since"] is None
    assert body["remaining_seconds"] == body["duration_seconds"]


def test_running_stamps_started_at_once(game_god, player):
    _patch(game_god, {"status": GameStatus.RUNNING})
    first = player.get(STATE_URL).json()["started_at"]
    assert first is not None

    _patch(game_god, {"status": GameStatus.PAUSED})
    _patch(game_god, {"status": GameStatus.RUNNING})
    assert player.get(STATE_URL).json()["started_at"] == first


def _run_for(minutes):
    """Put the game in running state as if it had been going for `minutes`."""
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    settings.running_since = timezone.now() - timedelta(minutes=minutes)
    settings.save(update_fields=["running_since"])
    return settings


def test_elapsed_counts_up_while_running(player):
    _run_for(30)
    assert player.get(STATE_URL).json()["elapsed_seconds"] == pytest.approx(1800, abs=5)


def test_remaining_is_the_duration_minus_elapsed(player, game_god):
    _patch(game_god, {"duration_minutes": 60})
    _run_for(10)

    body = player.get(STATE_URL).json()
    assert body["duration_seconds"] == 3600
    assert body["remaining_seconds"] == pytest.approx(3000, abs=5)


def test_remaining_never_goes_negative(player, game_god):
    _patch(game_god, {"duration_minutes": 5})
    _run_for(30)

    assert player.get(STATE_URL).json()["remaining_seconds"] == 0


def test_no_countdown_when_the_duration_is_zero(player, game_god):
    _patch(game_god, {"duration_minutes": 0})
    _run_for(10)

    assert player.get(STATE_URL).json()["remaining_seconds"] is None


# --- the timer stops with the game -------------------------------------------


def test_pausing_freezes_the_elapsed_timer(player, game_god):
    _run_for(20)
    _patch(game_god, {"status": GameStatus.PAUSED})

    frozen = player.get(STATE_URL).json()["elapsed_seconds"]
    assert frozen == pytest.approx(1200, abs=5)

    # Wind the ledger's clock: a paused game must not accrue any of it.
    settings = GameSettings.load()
    settings.running_since = timezone.now() - timedelta(hours=5)
    settings.save(update_fields=["running_since"])

    assert player.get(STATE_URL).json()["elapsed_seconds"] == frozen


def test_resuming_continues_from_where_it_stopped(player, game_god):
    _run_for(20)
    _patch(game_god, {"status": GameStatus.PAUSED})
    banked = GameSettings.load().accumulated_seconds
    assert banked == pytest.approx(1200, abs=5)

    _patch(game_god, {"status": GameStatus.RUNNING})
    resumed = player.get(STATE_URL).json()["elapsed_seconds"]
    assert resumed == pytest.approx(banked, abs=5)


def test_finishing_freezes_the_timer_too(player, game_god):
    _run_for(15)
    _patch(game_god, {"status": GameStatus.FINISHED})

    settings = GameSettings.load()
    assert settings.running_since is None
    assert player.get(STATE_URL).json()["elapsed_seconds"] == pytest.approx(900, abs=5)


def test_a_pause_does_not_eat_into_the_countdown(player, game_god):
    _patch(game_god, {"duration_minutes": 60})
    _run_for(10)
    _patch(game_god, {"status": GameStatus.PAUSED})

    settings = GameSettings.load()
    settings.running_since = timezone.now() - timedelta(hours=3)
    settings.save(update_fields=["running_since"])

    assert player.get(STATE_URL).json()["remaining_seconds"] == pytest.approx(3000, abs=5)


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


def test_a_superuser_is_not_automatically_a_game_god(client):
    """Being a Django admin is not the same as being trusted to run the event."""
    client.force_login(User.objects.create_superuser("root", password="secret"))
    assert client.get(SETTINGS_URL).status_code == 403
    assert _patch(client, {"status": GameStatus.RUNNING}).status_code == 403
    assert GameSettings.load().status == GameStatus.NOT_STARTED


def test_a_superuser_added_to_the_group_is_a_game_god(client):
    root = User.objects.create_superuser("root2", password="secret")
    root.groups.add(Group.objects.get(name="GameGods"))
    client.force_login(root)
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


def test_duration_is_settable(game_god, player):
    assert _patch(game_god, {"duration_minutes": 180}).status_code == 200
    assert player.get(STATE_URL).json()["duration_seconds"] == 10800


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


def test_the_design_lock_is_a_game_god_switch(game_god, player):
    assert _patch(game_god, {"design_locked": True}).status_code == 200
    assert GameSettings.load().design_locked is True
    assert player.get(STATE_URL).json()["design_locked"] is True

    _patch(game_god, {"design_locked": False})
    assert player.get(STATE_URL).json()["design_locked"] is False


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
    start = Node.objects.create(board=Board.GIRLS, code="L1_0", name="L1_0", level=spawn)
    house = Node.objects.create(board=Board.GIRLS, code="L1_2", name="L1_2", level=easy)

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
    assert response.json() == {
        "board": "all",
        "occupancies": 2,
        "submissions": 1,
        "entry_attempts": 0,
        "balance_events": 0,
        "sent_messages": 0,
        "duels": 0,
        "rooms_requeued": 0,
        "minesweeper_attempts": 0,
        "minesweeper_boards": 0,
        "teams": 1,
    }
    assert Occupancy.objects.count() == 0
    assert Submission.objects.count() == 0


def test_restart_clears_balance_events(game_god, team):
    from teams.models import BalanceEvent, BalanceReason

    BalanceEvent.objects.create(
        team=team, delta=400, balance_after=400, reason=BalanceReason.INITIAL
    )
    BalanceEvent.objects.create(
        team=team, delta=-20, balance_after=380, reason=BalanceReason.ENTRY, detail="L1_2"
    )

    response = _restart(game_god)

    assert response.status_code == 200
    assert response.json()["balance_events"] == 2
    assert BalanceEvent.objects.count() == 0


def test_restart_deletes_sent_messages_and_keeps_drafts(game_god):
    from notifications.models import Message, MessageStatus, Notification

    author = User.objects.create_user("announcer", password="x")
    draft = Message.objects.create(title="پیش‌نویس", body="نگه دار", sender=author)
    sent = Message.objects.create(
        title="ارسال‌شده",
        body="پاک شود",
        sender=author,
        status=MessageStatus.SENT,
        sent_at=timezone.now(),
    )
    Notification.objects.create(message=sent, user=author)

    response = _restart(game_god)

    assert response.status_code == 200
    assert response.json()["sent_messages"] == 1
    assert Message.objects.filter(status=MessageStatus.SENT).count() == 0
    assert Notification.objects.count() == 0
    draft.refresh_from_db()
    assert draft.title == "پیش‌نویس"
    assert draft.body == "نگه دار"
    assert draft.status == MessageStatus.DRAFT
    assert draft.sent_at is None


@pytest.fixture
def played_duel(played_board):
    """A closed duel pointing at one of the board's occupancies."""
    from django.contrib.auth.models import Permission

    from duels.models import Duel, DuelStatus, Room
    from game.models import Occupancy
    from teams.models import Team

    judge = User.objects.create_user("duel-judge", password="secret")
    judge.user_permissions.add(Permission.objects.get(codename="judge_duel"))
    room = Room.objects.create(
        name="Room 1",
        link="https://skyroom.test/reset-1",
        mentor=judge,
        last_assigned_at=timezone.now(),
    )
    defender = Team.objects.create(board=Board.GIRLS, code="defender", name="Defender", balance=100)
    target = Occupancy.objects.filter(team=played_board).order_by("pk").last()

    return Duel.objects.create(
        attacker=played_board,
        attacked=defender,
        node=target.node,
        target=target,
        floor=1,
        stake=400,
        room=room,
        mentor=judge,
        status=DuelStatus.CLOSED,
        winner=played_board,
        loser=defender,
        resolved_at=timezone.now(),
    )


def test_restart_survives_a_played_duel(game_god, played_duel):
    """`Duel.target` PROTECTs Occupancy, so one duel used to abort the whole restart."""
    from duels.models import Duel
    from game.models import Occupancy

    response = _restart(game_god)

    assert response.status_code == 200, response.content
    assert response.json()["duels"] == 1
    assert Duel.objects.count() == 0
    assert Occupancy.objects.count() == 0


def test_restart_keeps_the_rooms_but_clears_their_place_in_the_queue(game_god, played_duel):
    """An organiser typed the Skyroom link and picked the judge; that is content."""
    from duels.models import Room

    assert _restart(game_god).json()["rooms_requeued"] == 1

    room = Room.objects.get()
    assert room.is_active is True
    assert room.link == "https://skyroom.test/reset-1"
    # Cleared, so the rotation starts fresh rather than carrying last run's order.
    assert room.last_assigned_at is None


def test_restart_clears_toll_crossings(game_god, team):
    """A crossing opens the one-way road past a gate; keeping it hands out the
    outer rings for free on the next run."""
    from game.models import LevelConfig, Node
    from minesweeper.crossings import cleared_node_codes
    from minesweeper.models import (
        DifficultyConfig,
        MinesweeperAttempt,
        MinesweeperGame,
        MinesweeperStatus,
    )

    toll = LevelConfig.objects.get(level="toll")
    gate = Node.objects.create(board=Board.GIRLS, code="C34_9", name="Gate", level=toll)
    difficulty = DifficultyConfig.objects.first()
    board = MinesweeperGame.objects.create(
        node=gate,
        difficulty=difficulty,
        width=difficulty.width,
        height=difficulty.height,
        mine_count=difficulty.mine_count,
        base_score=difficulty.base_score,
    )
    MinesweeperAttempt.objects.create(
        game=board,
        team=team,
        status=MinesweeperStatus.WON,
        finished_at=timezone.now(),
    )

    assert cleared_node_codes(team) == ["C34_9"]

    assert _restart(game_god).json()["minesweeper_attempts"] == 1
    assert cleared_node_codes(team) == []


def test_restart_clears_the_entry_sheets(game_god, team):
    """Left behind, last run's correct answers would open the gate for free."""
    from game.models import EntryAttempt, EntryQuestion

    question = EntryQuestion.objects.create(
        code="entry-1", title="یک", body="۱+۱ چند است؟", answer=2
    )
    EntryAttempt.objects.create(
        team=team,
        question=question,
        position=1,
        answer=2,
        is_correct=True,
        answered_at=timezone.now(),
    )

    assert _restart(game_god).json()["entry_attempts"] == 1
    assert EntryAttempt.objects.count() == 0
    # The bank is content, not run state.
    assert EntryQuestion.objects.count() == 1


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


def test_restart_keeps_the_duration(game_god):
    """It is the length of the game, not a fact about the run that just ended."""
    _patch(game_god, {"duration_minutes": 90})
    _restart(game_god)
    assert GameSettings.load().duration_minutes == 90


def test_restart_zeroes_both_timers(game_god, player):
    _patch(game_god, {"duration_minutes": 60})
    _run_for(25)
    _patch(game_god, {"status": GameStatus.PAUSED})
    assert GameSettings.load().accumulated_seconds > 0

    _restart(game_god)

    body = player.get(STATE_URL).json()
    assert body["elapsed_seconds"] is None
    assert body["accumulated_seconds"] == 0
    assert body["running_since"] is None
    assert body["remaining_seconds"] == 3600


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


def test_a_running_row_without_an_open_stretch_heals_itself(player):
    """A hand-edited or migrated row must not leave the timer stuck at zero."""
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])

    # Simulate the inconsistent state: running, but no stretch open.
    GameSettings.objects.filter(pk=settings.pk).update(running_since=None)
    stuck = GameSettings.load()
    assert stuck.elapsed_seconds == 0

    stuck.save()
    stuck.refresh_from_db()
    assert stuck.running_since is not None
