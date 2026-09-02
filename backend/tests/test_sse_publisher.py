"""The publisher is fire-and-forget: an unreachable Redis costs updates, not moves."""

import logging

import pytest
import redis
from django.contrib.auth.models import Group
from django.utils import timezone

from game.models import (
    AnswerType,
    Edge,
    GameSettings,
    GameStatus,
    LevelConfig,
    Node,
    Occupancy,
    Question,
    ReleaseReason,
)
from game.services import events
from game.services.mentor import grade_attempt, release_attempt
from game.services.movement import claim_node, claim_spawn
from game.services.questions import grade_submission, submit_answer
from teams.models import Team
from teams.start_colors import color_for_start

pytestmark = pytest.mark.django_db

START_CODE = "L1_0"


@pytest.fixture
def running_game():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture
def nodes():
    levels = {row.pk: row for row in LevelConfig.objects.all()}
    codes = {START_CODE: "spawn", "e1": "easy"}
    made = {
        code: Node.objects.create(code=code, name=code, level=levels[level])
        for code, level in codes.items()
    }
    Edge.objects.create(a=made[START_CODE], b=made["e1"])
    return made


@pytest.fixture
def questions(nodes):
    return [
        Question.objects.create(
            level=LevelConfig.objects.get(level="easy"),
            code=f"q-easy-{index}",
            title=f"Q {index}",
            body="Body",
            answer_type=AnswerType.TEXT,
            answer_key="k",
        )
        for index in range(3)
    ]


@pytest.fixture
def team(nodes):
    return Team.objects.create(
        code="alpha", name="Alpha", balance=500, color=color_for_start(START_CODE)
    )


@pytest.fixture
def recorded(monkeypatch):
    """Capture publish() calls without a Redis. publish_on_commit resolves the
    name from the module at call time, so patching the attribute is enough."""
    calls = []
    monkeypatch.setattr(events, "publish", lambda kind, payload=None: calls.append((kind, payload)))
    return calls


def test_publish_is_a_noop_without_redis(settings, monkeypatch):
    settings.REDIS_URL = ""

    def explode():
        raise AssertionError("no client should be built when REDIS_URL is unset")

    monkeypatch.setattr(events, "_get_client", explode)

    assert events.publish(events.BOARD_GRADED, {"node": "e1"}) is None
    assert events.current_version() is None


def test_publish_swallows_a_dead_redis(settings, monkeypatch, caplog):
    settings.REDIS_URL = "redis://127.0.0.1:6379/0"

    def broken():
        raise redis.ConnectionError("nope")

    monkeypatch.setattr(events, "_get_client", broken)

    with caplog.at_level(logging.WARNING, logger="karsoogh"):
        assert events.publish(events.BOARD_GRADED, {"node": "e1"}) is None

    assert "SSE publish failed" in caplog.text


def test_a_dead_redis_does_not_fail_the_move(
    settings, monkeypatch, running_game, nodes, team, django_capture_on_commit_callbacks
):
    settings.REDIS_URL = "redis://127.0.0.1:6379/0"
    monkeypatch.setattr(
        events, "_get_client", lambda: (_ for _ in ()).throw(redis.ConnectionError("nope"))
    )

    with django_capture_on_commit_callbacks(execute=True):
        holding = claim_spawn(team, nodes[START_CODE])

    assert Occupancy.objects.active().filter(pk=holding.pk).exists()


def test_claim_spawn_publishes_once_and_is_idempotent(
    running_game, nodes, team, recorded, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        claim_spawn(team, nodes[START_CODE])
    with django_capture_on_commit_callbacks(execute=True):
        claim_spawn(team, nodes[START_CODE])

    assert [kind for kind, _ in recorded] == [events.BOARD_SPAWN_CLAIMED]
    assert recorded[0][1] == {"team": "alpha", "node": START_CODE}


def test_claim_node_publishes_the_move_and_the_question(
    running_game, nodes, questions, team, recorded, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        claim_spawn(team, nodes[START_CODE])
    recorded.clear()

    with django_capture_on_commit_callbacks(execute=True):
        claim_node(team, nodes["e1"])

    kinds = [kind for kind, _ in recorded]
    assert kinds == [events.QUESTION_ASSIGNED, events.BOARD_NODE_CLAIMED]


def test_release_publishes_the_reason(
    running_game, nodes, team, recorded, django_capture_on_commit_callbacks
):
    holding = Occupancy.objects.create(
        team=team, node=nodes["e1"], slot=1, question_assigned_at=timezone.now()
    )
    recorded.clear()

    with django_capture_on_commit_callbacks(execute=True):
        release_attempt(holding, ReleaseReason.EXPIRED)

    assert recorded == [
        (events.BOARD_RELEASED, {"team": "alpha", "node": "e1", "reason": ReleaseReason.EXPIRED})
    ]


def test_grade_publishes_even_when_no_floor_is_awarded(
    running_game, nodes, team, recorded, django_capture_on_commit_callbacks
):
    """A zero grade takes the early return before the re-rank; it still announces."""
    holding = Occupancy.objects.create(
        team=team, node=nodes["e1"], slot=1, question_assigned_at=timezone.now()
    )

    with django_capture_on_commit_callbacks(execute=True):
        grade_attempt(holding, 0)

    assert recorded == [(events.BOARD_GRADED, {"node": "e1"})]


def test_zero_grade_submission_publishes_grade_then_release(
    django_user_model,
    running_game,
    nodes,
    questions,
    team,
    recorded,
    django_capture_on_commit_callbacks,
):
    Group.objects.get(name="Mentors")
    user = django_user_model.objects.create_user("alpha-user", password="x", team=team)
    with django_capture_on_commit_callbacks(execute=True):
        claim_spawn(team, nodes[START_CODE])
        claim_node(team, nodes["e1"])
    holding = Occupancy.objects.active().get(team=team, node=nodes["e1"])
    with django_capture_on_commit_callbacks(execute=True):
        submission = submit_answer(holding, user, body="42")
    recorded.clear()

    with django_capture_on_commit_callbacks(execute=True):
        grade_submission(submission, 0)

    assert [kind for kind, _ in recorded] == [events.BOARD_GRADED, events.BOARD_RELEASED]


def test_submission_publishes_for_mentors(
    django_user_model,
    running_game,
    nodes,
    questions,
    team,
    recorded,
    django_capture_on_commit_callbacks,
):
    user = django_user_model.objects.create_user("alpha-user", password="x", team=team)
    with django_capture_on_commit_callbacks(execute=True):
        claim_spawn(team, nodes[START_CODE])
        claim_node(team, nodes["e1"])
    holding = Occupancy.objects.active().get(team=team, node=nodes["e1"])
    recorded.clear()

    with django_capture_on_commit_callbacks(execute=True):
        submission = submit_answer(holding, user, body="42")

    assert recorded == [(events.SUBMISSION_CREATED, {"submission": submission.pk, "team": "alpha"})]
