"""Question assignment, submission, and mentor grading API tests."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from game.exceptions import NoQuestionAvailable
from game.models import AnswerType, GameSettings, GameStatus, LevelConfig, Node, Occupancy, Question
from game.services import assign_question, grade_submission, submit_answer
from teams.models import Team

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def easy():
    return LevelConfig.objects.get(level="easy")


@pytest.fixture
def hard():
    return LevelConfig.objects.get(level="hard")


@pytest.fixture
def node(easy):
    return Node.objects.create(code="e1", name="Easy 1", level=easy)


@pytest.fixture
def teams():
    return [Team.objects.create(code=f"t{i}", name=f"Team {i}") for i in range(3)]


@pytest.fixture
def running_game():
    settings_row = GameSettings.load()
    settings_row.status = GameStatus.RUNNING
    settings_row.save(update_fields=["status"])
    return settings_row


@pytest.fixture
def questions(easy):
    return [
        Question.objects.create(
            level=easy,
            code=f"q{i}",
            title=f"Question {i}",
            body=f"Body {i}",
            answer_type=AnswerType.TEXT,
            answer_key=f"key{i}",
            is_active=True,
        )
        for i in range(1, 4)
    ]


def make_user(team, username, *, staff=False):
    user = User.objects.create_user(
        username=username,
        password="pw",
        team=team,
        is_staff=staff,
    )
    if staff:
        user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Occupancy),
                codename="act_as_mentor",
            )
        )
    return user


def occupy(node, team, **kwargs):
    kwargs.setdefault("slot", 1)
    return Occupancy.objects.create(node=node, team=team, **kwargs)


class TestAssignQuestion:
    def test_no_repeat_per_team(self, easy, teams, questions, running_game):
        nodes = [Node.objects.create(code=f"n{i}", name=f"N{i}", level=easy) for i in range(4)]
        assigned = []
        for i in range(3):
            occ = occupy(nodes[i], teams[0])
            assigned.append(assign_question(occ))

        assert len({question.pk for question in assigned}) == 3

        occ4 = occupy(nodes[3], teams[0])
        with pytest.raises(NoQuestionAvailable):
            assign_question(occ4)

    def test_idempotent_on_same_occupancy(self, node, teams, questions, running_game):
        occ = occupy(node, teams[0])
        first = assign_question(occ)
        second = assign_question(occ)
        assert first.pk == second.pk


class TestOccupancyQuestionAPI:
    def test_team_can_read_assigned_question(self, node, teams, questions, running_game):
        user = make_user(teams[0], "u0")
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.refresh_from_db()

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(f"/api/occupancies/{occ.pk}/question/")

        assert response.status_code == 200
        assert response.data["question"]["code"] == occ.question.code
        assert "answer_key" not in response.data["question"]
        assert response.data["remaining_seconds"] >= 0

    def test_other_team_cannot_read(self, node, teams, questions, running_game):
        occ = occupy(node, teams[0])
        assign_question(occ)
        other = make_user(teams[1], "u1")

        client = APIClient()
        client.force_authenticate(user=other)
        response = client.get(f"/api/occupancies/{occ.pk}/question/")

        assert response.status_code == 403


class TestSubmitAPI:
    def test_submit_once_then_conflict(self, node, teams, questions, running_game):
        user = make_user(teams[0], "u0")
        occ = occupy(node, teams[0])
        assign_question(occ)

        client = APIClient()
        client.force_authenticate(user=user)
        first = client.post(f"/api/occupancies/{occ.pk}/submit/", {"body": "answer"}, format="json")
        second = client.post(f"/api/occupancies/{occ.pk}/submit/", {"body": "again"}, format="json")

        assert first.status_code == 201
        assert second.status_code == 409

    def test_submit_after_expiry_returns_409(self, node, teams, questions, running_game):
        user = make_user(teams[0], "u0")
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.expires_at = timezone.now() - timedelta(minutes=1)
        occ.save(update_fields=["expires_at"])

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/occupancies/{occ.pk}/submit/", {"body": "late"}, format="json"
        )

        assert response.status_code == 409

    def test_submit_when_game_not_running_returns_409(self, node, teams, questions, running_game):
        user = make_user(teams[0], "u0")
        occ = occupy(node, teams[0])
        assign_question(occ)
        running_game.status = GameStatus.PAUSED
        running_game.save(update_fields=["status"])

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(
            f"/api/occupancies/{occ.pk}/submit/", {"body": "answer"}, format="json"
        )

        assert response.status_code == 409

    def test_other_team_cannot_submit(self, node, teams, questions, running_game):
        occ = occupy(node, teams[0])
        assign_question(occ)
        other = make_user(teams[1], "u1")

        client = APIClient()
        client.force_authenticate(user=other)
        response = client.post(
            f"/api/occupancies/{occ.pk}/submit/", {"body": "hack"}, format="json"
        )

        assert response.status_code == 403


class TestMentorGradingAPI:
    def test_pending_queue_and_grade(self, node, teams, questions, running_game):
        user = make_user(teams[0], "player")
        mentor = make_user(None, "mentor", staff=True)
        occ = occupy(node, teams[0], floor=1)
        assign_question(occ)
        occ.refresh_from_db()
        submission = submit_answer(occ, user, body="42")

        client = APIClient()
        client.force_authenticate(user=mentor)
        listing = client.get("/api/submissions/")
        detail = client.get(f"/api/submissions/{submission.pk}/")
        grade = client.post(
            f"/api/submissions/{submission.pk}/grade/", {"grade": 50}, format="json"
        )

        assert listing.status_code == 200
        assert any(row["id"] == submission.pk for row in listing.data)
        assert detail.status_code == 200
        assert detail.data["question"]["answer_key"] == occ.question.answer_key
        assert grade.status_code == 200
        assert grade.data["points"] == 50

        occ.refresh_from_db()
        assert occ.grade == 50
        assert occ.points == 50

    def test_grade_zero_releases_occupancy(self, hard, teams, questions, running_game):
        hard_node = Node.objects.create(code="h1", name="Hard 1", level=hard)
        hard_q = Question.objects.create(
            level=hard,
            code="hq1",
            title="Hard Q",
            body="Hard body",
            answer_type=AnswerType.TEXT,
            is_active=True,
        )
        user = make_user(teams[0], "player2")
        occ = occupy(hard_node, teams[0], floor=1)
        assign_question(occ)
        occ.question = hard_q
        occ.save(update_fields=["question"])
        submission = submit_answer(occ, user, body="wrong")

        grade_submission(submission, 0)
        occ.refresh_from_db()
        assert occ.released_at is not None
        assert occ.release_reason == "zero_grade"


class TestMediaAccess:
    def test_other_team_cannot_download_submission_file(self, node, teams, running_game):
        file_question = Question.objects.create(
            level=node.level,
            code="fq1",
            title="File Q",
            body="Upload",
            answer_type=AnswerType.FILE,
            is_active=True,
        )
        user = make_user(teams[0], "file-user")
        other = make_user(teams[1], "file-other")
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.question = file_question
        occ.save(update_fields=["question"])

        upload = SimpleUploadedFile("proof.txt", b"hello", content_type="text/plain")
        submission = submit_answer(occ, user, file=upload)

        client = APIClient()
        client.force_authenticate(user=other)
        response = client.get(f"/api/media/submissions/{submission.pk}/")

        assert response.status_code == 403

        client.force_authenticate(user=user)
        allowed = client.get(f"/api/media/submissions/{submission.pk}/")
        assert allowed.status_code == 200
