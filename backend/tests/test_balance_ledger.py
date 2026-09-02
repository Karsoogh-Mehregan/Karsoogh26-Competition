"""Balance ledger: every گیلاریوم change is stored and listed for the team."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from game.models import (
    AnswerType,
    Edge,
    GameSettings,
    GameStatus,
    LevelConfig,
    Node,
    Occupancy,
    Question,
)
from game.services import assign_question, claim_node, grade_submission, submit_answer
from teams.models import BalanceEvent, BalanceReason, Team

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def running_game():
    settings_row = GameSettings.load()
    settings_row.status = GameStatus.RUNNING
    settings_row.save(update_fields=["status"])
    return settings_row


@pytest.fixture
def easy():
    return LevelConfig.objects.get(level="easy")


@pytest.fixture
def node(easy):
    return Node.objects.create(code="e1", name="Easy 1", level=easy)


@pytest.fixture
def spawn():
    return LevelConfig.objects.get(level="spawn")


@pytest.fixture
def spawn_node(spawn):
    return Node.objects.create(code="s1", name="Start 1", level=spawn)


@pytest.fixture
def team():
    return Team.objects.create(code="alpha", name="Alpha", balance=500)


@pytest.fixture
def other():
    return Team.objects.create(code="beta", name="Beta", balance=500)


def make_user(team, username):
    return User.objects.create_user(username=username, password="pw", team=team)


def link(a: Node, b: Node) -> Edge:
    lower, upper = sorted((a, b), key=lambda item: item.pk)
    return Edge.objects.create(a=lower, b=upper, directed=False)


class TestBalanceLedger:
    def test_entry_cost_writes_a_log_row(self, running_game, node, spawn_node, team):
        Occupancy.objects.create(node=spawn_node, team=team, slot=1, is_spawn=True)
        link(spawn_node, node)
        Question.objects.create(
            level=node.level,
            code="q1",
            title="Q",
            body="B",
            answer_type=AnswerType.TEXT,
            answer_key="k",
            is_active=True,
        )

        claim_node(team, node)

        event = BalanceEvent.objects.get(team=team)
        cost = LevelConfig.objects.get(level="easy").entry_cost
        assert event.delta == -cost
        assert event.reason == BalanceReason.ENTRY
        assert event.detail == "Easy 1"
        assert event.balance_after == 500 - cost

    def test_own_team_lists_events(self, team):
        BalanceEvent.objects.create(
            team=team,
            delta=400,
            balance_after=400,
            reason=BalanceReason.INITIAL,
        )
        user = make_user(team, "alpha-user")
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get("/api/teams/alpha/balance-events/")
        assert response.status_code == 200
        assert len(response.data) == 1
        row = response.data[0]
        assert row["delta"] == 400
        assert row["reason"] == "initial"
        assert row["reason_label"] == "موجودی اولیه"

    def test_other_team_is_forbidden(self, team, other):
        user = make_user(other, "beta-user")
        client = APIClient()
        client.force_authenticate(user=user)
        assert client.get("/api/teams/alpha/balance-events/").status_code == 403

    def test_grade_writes_a_payout_row(self, running_game, node, team):
        user = make_user(team, "alpha-user")
        occ = Occupancy.objects.create(node=node, team=team, slot=1)
        Question.objects.create(
            level=node.level,
            code="q1",
            title="Q",
            body="B",
            answer_type=AnswerType.TEXT,
            answer_key="k",
            is_active=True,
        )
        assign_question(occ)
        submit_answer(occ, user, body="42")
        occ.refresh_from_db()
        grade_submission(occ.submission, 100)

        event = BalanceEvent.objects.get(team=team, reason=BalanceReason.GRADE)
        assert event.delta > 0
        assert event.detail == "Easy 1"
        team.refresh_from_db()
        assert event.balance_after == team.balance


class TestLevelList:
    def test_lists_entry_costs(self, team):
        user = make_user(team, "alpha-user")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/levels/")
        assert response.status_code == 200
        by_level = {row["level"]: row["entry_cost"] for row in response.data}
        assert by_level["easy"] == LevelConfig.objects.get(level="easy").entry_cost
        assert by_level["spawn"] == 0
