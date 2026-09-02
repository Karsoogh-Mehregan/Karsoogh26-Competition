"""Team attempts list API."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from game.models import AnswerType, GameSettings, GameStatus, LevelConfig, Node, Occupancy, Question
from game.services import assign_question, submit_answer
from teams.models import Team

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def easy():
    return LevelConfig.objects.get(level="easy")


@pytest.fixture
def spawn():
    return LevelConfig.objects.get(level="spawn")


@pytest.fixture
def node(easy):
    return Node.objects.create(code="e1", name="Easy 1", level=easy)


@pytest.fixture
def spawn_node(spawn):
    return Node.objects.create(code="s1", name="Start 1", level=spawn)


@pytest.fixture
def teams():
    return [
        Team.objects.create(code="alpha", name="Alpha"),
        Team.objects.create(code="beta", name="Beta"),
    ]


@pytest.fixture
def running_game():
    settings_row = GameSettings.load()
    settings_row.status = GameStatus.RUNNING
    settings_row.save(update_fields=["status"])
    return settings_row


@pytest.fixture
def question(easy):
    return Question.objects.create(
        level=easy,
        code="q1",
        title="Question 1",
        body="Body 1",
        answer_type=AnswerType.TEXT,
        answer_key="secret",
        is_active=True,
    )


def make_user(team, username):
    return User.objects.create_user(username=username, password="pw", team=team)


def occupy(node, team, **kwargs):
    kwargs.setdefault("slot", 1)
    return Occupancy.objects.create(node=node, team=team, **kwargs)


class TestTeamAttemptsAPI:
    def test_own_team_lists_attempts(self, node, teams, question, running_game):
        user = make_user(teams[0], "alpha-user")
        occ = occupy(node, teams[0])
        assign_question(occ)

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/teams/alpha/attempts/")

        assert response.status_code == 200
        assert len(response.data) == 1
        row = response.data[0]
        assert row["id"] == occ.pk
        assert row["node_code"] == "e1"
        assert row["status"] == "open"
        assert row["question"]["code"] == "q1"
        assert "answer_key" not in row["question"]
        assert row["submission"] is None
        assert row["remaining_seconds"] >= 0

    def test_other_team_gets_403(self, node, teams, question, running_game):
        user = make_user(teams[1], "beta-user")
        occ = occupy(node, teams[0])
        assign_question(occ)

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/teams/alpha/attempts/")

        assert response.status_code == 403

    def test_spawn_has_no_question(self, spawn_node, teams, running_game):
        user = make_user(teams[0], "alpha-user")
        occupy(spawn_node, teams[0], is_spawn=True)

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/teams/alpha/attempts/")

        assert response.status_code == 200
        assert len(response.data) == 1
        row = response.data[0]
        assert row["is_spawn"] is True
        assert row["question"] is None
        assert row["status"] == "no_question"

    def test_answered_status_after_submit(self, node, teams, question, running_game):
        user = make_user(teams[0], "alpha-user")
        occ = occupy(node, teams[0])
        assign_question(occ)
        submit_answer(occ, user, body="42")

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/teams/alpha/attempts/")

        assert response.status_code == 200
        row = response.data[0]
        assert row["status"] == "answered"
        assert row["submission"]["id"] is not None
        assert row["submission"]["submitted_at"] is not None

    def test_expired_status_when_window_closed(self, node, teams, question, running_game):
        user = make_user(teams[0], "alpha-user")
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.expires_at = timezone.now() - timedelta(minutes=1)
        occ.save(update_fields=["expires_at"])

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get("/api/teams/alpha/attempts/")

        assert response.status_code == 200
        row = response.data[0]
        assert row["status"] == "expired"
        assert row["is_expired"] is True
        assert row["remaining_seconds"] == 0
