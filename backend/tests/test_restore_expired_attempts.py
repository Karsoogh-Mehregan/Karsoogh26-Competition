from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.boards import Board
from game.models import (
    AnswerType,
    LevelConfig,
    Node,
    Occupancy,
    Question,
    ReleaseReason,
)
from teams.models import Team

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    easy = LevelConfig.objects.get(level="easy")
    node = Node.objects.create(board=Board.GIRLS, code="e1", level=easy)
    team = Team.objects.create(board=Board.GIRLS, code="alpha", name="A")
    other = Team.objects.create(board=Board.GIRLS, code="beta", name="B")
    q = Question.objects.create(
        level=easy, title="q", body="b", answer_type=AnswerType.TEXT, max_grade=100
    )
    return node, team, other, q


def make(node, team, q, *, released, ago_minutes, slot):
    now = timezone.now()
    return Occupancy.objects.create(
        node=node,
        team=team,
        slot=slot,
        question=q,
        question_assigned_at=now - timedelta(minutes=ago_minutes + 10),
        expires_at=now - timedelta(minutes=ago_minutes),
        released_at=now - timedelta(minutes=ago_minutes) if released else None,
        release_reason=ReleaseReason.EXPIRED if released else "",
    )


def test_restores_and_reclocks(setup):
    node, team, other, q = setup
    swept = make(node, team, q, released=True, ago_minutes=20, slot=1)
    pending = make(node, other, q, released=False, ago_minutes=5, slot=2)
    old = make(node, other, q, released=True, ago_minutes=200, slot=3)

    out = StringIO()
    call_command("restore_expired_attempts", "--minutes", "15", stdout=out)

    swept.refresh_from_db()
    pending.refresh_from_db()
    old.refresh_from_db()
    now = timezone.now()
    assert swept.released_at is None and swept.release_reason == ""
    assert swept.expires_at > now
    assert pending.expires_at > now
    assert old.released_at is not None
    assert "2 reopened, 0 skipped" in out.getvalue()


def test_skips_taken_slot(setup):
    node, team, other, q = setup
    swept = make(node, team, q, released=True, ago_minutes=10, slot=1)
    Occupancy.objects.create(node=node, team=other, slot=1)

    out = StringIO()
    call_command("restore_expired_attempts", stdout=out)
    swept.refresh_from_db()
    assert swept.released_at is not None
    assert "slot taken since" in out.getvalue()


def test_dry_run_changes_nothing(setup):
    node, team, _other, q = setup
    swept = make(node, team, q, released=True, ago_minutes=10, slot=1)
    call_command("restore_expired_attempts", "--dry-run", stdout=StringIO())
    swept.refresh_from_db()
    assert swept.released_at is not None
