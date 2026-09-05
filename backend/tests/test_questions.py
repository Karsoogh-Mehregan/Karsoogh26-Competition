"""Question assignment, submission, and mentor grading API tests."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from core.boards import Board
from game.exceptions import NoQuestionAvailable
from game.models import AnswerType, GameSettings, GameStatus, LevelConfig, Node, Occupancy, Question
from game.services import assign_question, grade_attempt, grade_submission, submit_answer
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
    return Node.objects.create(board=Board.GIRLS, code="e1", name="Easy 1", level=easy)


@pytest.fixture
def teams():
    return [
        Team.objects.create(board=Board.GIRLS, code=f"t{i}", name=f"Team {i}") for i in range(3)
    ]


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


def assign_to_mentor(occupancy, mentor):
    """Point the holding's question at this mentor (API queue is assignment-scoped)."""
    occupancy.refresh_from_db()
    occupancy.question.mentor = mentor
    occupancy.question.save(update_fields=["mentor"])
    return occupancy.question


def occupy(node, team, **kwargs):
    kwargs.setdefault("slot", 1)
    return Occupancy.objects.create(node=node, team=team, **kwargs)


class TestAssignQuestion:
    def test_no_repeat_per_team(self, easy, teams, questions, running_game):
        nodes = [
            Node.objects.create(board=Board.GIRLS, code=f"n{i}", name=f"N{i}", level=easy)
            for i in range(4)
        ]
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

    def test_expiry_follows_the_node_level_ttl(self, node, teams, questions, running_game, easy):
        easy.attempt_ttl_minutes = 7
        easy.save(update_fields=["attempt_ttl_minutes"])
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.refresh_from_db()
        assert occ.expires_at - occ.question_assigned_at == timedelta(minutes=7)


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
        occ = occupy(node, teams[0])
        assign_question(occ)
        assign_to_mentor(occ, mentor)
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
        assert detail.data["question"]["max_grade"] == 100
        assert grade.status_code == 200
        # 50 of 100 on the easy floor-1 reward of 100, then the slot goes back.
        assert grade.data["awarded"] == 50
        assert grade.data["points"] == 0
        assert grade.data["release_reason"] == "partial_grade"

        occ.refresh_from_db()
        assert occ.grade == 50
        assert occ.floor is None
        assert occ.released_at is not None
        assert Team.objects.get(pk=teams[0].pk).balance == 50

    def test_full_marks_keep_the_floor(self, node, teams, questions, running_game):
        user = make_user(teams[0], "player")
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.refresh_from_db()
        submission = submit_answer(occ, user, body="42")

        grade_submission(submission, occ.question.max_grade)

        occ.refresh_from_db()
        assert occ.floor == 1
        assert occ.released_at is None
        assert Team.objects.get(pk=teams[0].pk).balance == 100

    def test_partial_marks_pay_the_ratio_of_the_floor(self, node, teams, questions, running_game):
        """5 of a max_grade of 10 is half the easy floor-1 reward of 100."""
        Question.objects.filter(pk__in=[q.pk for q in questions]).update(max_grade=10)
        user = make_user(teams[0], "player")
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.refresh_from_db()
        submission = submit_answer(occ, user, body="42")

        occ = grade_submission(submission, 5)

        assert occ.grade_multiplier == Decimal("0.500")
        assert occ.awarded == 50
        assert occ.release_reason == "partial_grade"
        assert Team.objects.get(pk=teams[0].pk).balance == 50

    def test_partial_marks_leave_the_tower_alone(self, hard, teams, running_game):
        """A grade short of full marks pays but must not shuffle the floors above it.

        Ranking it would push the floor-1 holder up to floor 2 and then leave
        floor 1 empty when the partial holding is released.
        """
        hard_node = Node.objects.create(board=Board.GIRLS, code="h3", name="Hard 3", level=hard)
        hard_question = Question.objects.create(
            level=hard,
            code="hq3",
            title="Hard Q",
            body="Hard body",
            answer_type=AnswerType.TEXT,
            answer_key="key",
            is_active=True,
        )
        assigned = timezone.now()
        winner = occupy(
            hard_node,
            teams[0],
            slot=1,
            floor=1,
            grade=100,
            grade_multiplier=Decimal("1.000"),
            question_assigned_at=assigned,
        )
        partial = occupy(
            hard_node,
            teams[1],
            slot=2,
            question=hard_question,
            question_assigned_at=assigned + timedelta(seconds=1),
        )

        partial = grade_attempt(partial, 90)

        winner.refresh_from_db()
        assert winner.floor == 1
        assert Team.objects.get(pk=teams[0].pk).balance == 0
        assert partial.floor is None
        assert partial.release_reason == "partial_grade"
        # The floor it would have taken is 2, worth 450 at 0.9 of the ratio.
        assert partial.awarded == 405
        assert Team.objects.get(pk=teams[1].pk).balance == 405

    def test_grade_above_the_question_scale_is_refused(self, node, teams, questions, running_game):
        Question.objects.filter(pk__in=[q.pk for q in questions]).update(max_grade=10)
        user = make_user(teams[0], "player")
        mentor = make_user(None, "mentor", staff=True)
        occ = occupy(node, teams[0])
        assign_question(occ)
        assign_to_mentor(occ, mentor)
        submission = submit_answer(Occupancy.objects.get(pk=occ.pk), user, body="42")

        client = APIClient()
        client.force_authenticate(user=mentor)
        response = client.post(
            f"/api/submissions/{submission.pk}/grade/", {"grade": 11}, format="json"
        )

        assert response.status_code == 422
        assert Occupancy.objects.get(pk=occ.pk).grade is None

    def test_the_better_ratio_takes_the_higher_floor(self, hard, teams, running_game):
        """Raw grades across two scales are incomparable; the ratio is what ranks.

        8 of 10 outranks 50 of 100 even though 8 < 50. The two are seeded as
        already-graded rows and a third grade triggers the re-rank, because the
        release rule would otherwise retire both before they ever share a tower.
        """
        hard_node = Node.objects.create(board=Board.GIRLS, code="h2", name="Hard 2", level=hard)
        assigned = timezone.now()
        for slot, (team, grade, ratio) in enumerate(
            ((teams[0], 8, "0.800"), (teams[1], 50, "0.500")), start=1
        ):
            occupy(
                hard_node,
                team,
                slot=slot,
                grade=grade,
                grade_multiplier=Decimal(ratio),
                question_assigned_at=assigned + timedelta(seconds=slot),
            )
        trigger = occupy(
            hard_node, teams[2], slot=3, question_assigned_at=assigned + timedelta(seconds=3)
        )

        grade_attempt(trigger, 0)

        floors = {
            occ.team.code: occ.floor
            for occ in Occupancy.objects.filter(node=hard_node).select_related("team")
        }
        assert floors == {teams[0].code: 2, teams[1].code: 1, teams[2].code: None}

    def test_grade_zero_releases_occupancy(self, hard, teams, questions, running_game):
        hard_node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
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

    def test_weak_reasoning_zeros_grade_and_takes_ten_percent(
        self, node, teams, questions, running_game
    ):
        from teams.models import BalanceEvent, BalanceReason

        team = teams[0]
        team.balance = 405
        team.save(update_fields=["balance"])
        user = make_user(team, "weak-player")
        mentor = make_user(None, "weak-mentor", staff=True)
        occ = occupy(node, team)
        assign_question(occ)
        assign_to_mentor(occ, mentor)
        submission = submit_answer(Occupancy.objects.get(pk=occ.pk), user, body="nah")

        client = APIClient()
        client.force_authenticate(user=mentor)
        response = client.post(
            f"/api/submissions/{submission.pk}/grade/",
            {"grade": 0, "weak_reasoning": True},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["grade"] == 0
        assert response.data["penalty"] == 41  # 10% of 405, half-up
        assert response.data["release_reason"] == "zero_grade"

        occ.refresh_from_db()
        assert occ.grade == 0
        assert occ.released_at is not None
        assert Team.objects.get(pk=team.pk).balance == 364

        event = BalanceEvent.objects.get(team=team, reason=BalanceReason.WEAK_REASONING)
        assert event.delta == -41
        assert event.detail == node.code

    def test_weak_reasoning_refuses_nonzero_grade(self, node, teams, questions, running_game):
        user = make_user(teams[0], "weak-player2")
        mentor = make_user(None, "weak-mentor2", staff=True)
        occ = occupy(node, teams[0])
        assign_question(occ)
        assign_to_mentor(occ, mentor)
        submission = submit_answer(Occupancy.objects.get(pk=occ.pk), user, body="nah")

        client = APIClient()
        client.force_authenticate(user=mentor)
        response = client.post(
            f"/api/submissions/{submission.pk}/grade/",
            {"grade": 10, "weak_reasoning": True},
            format="json",
        )

        assert response.status_code == 400
        assert Occupancy.objects.get(pk=occ.pk).grade is None


class TestMentorQuestionAssignment:
    def test_assigned_question_only_visible_to_that_mentor(
        self, node, teams, questions, running_game
    ):
        user = make_user(teams[0], "player-asgn")
        owner = make_user(None, "mentor-owner", staff=True)
        other = make_user(None, "mentor-other", staff=True)
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.refresh_from_db()
        occ.question.mentor = owner
        occ.question.save(update_fields=["mentor"])
        submission = submit_answer(occ, user, body="42")

        client = APIClient()
        client.force_authenticate(user=owner)
        own_list = client.get("/api/submissions/")
        own_detail = client.get(f"/api/submissions/{submission.pk}/")
        assert own_list.status_code == 200
        assert any(row["id"] == submission.pk for row in own_list.data)
        assert own_detail.status_code == 200

        client.force_authenticate(user=other)
        other_list = client.get("/api/submissions/")
        other_detail = client.get(f"/api/submissions/{submission.pk}/")
        other_grade = client.post(
            f"/api/submissions/{submission.pk}/grade/", {"grade": 50}, format="json"
        )
        assert other_list.status_code == 200
        assert all(row["id"] != submission.pk for row in other_list.data)
        assert other_detail.status_code == 404
        assert other_grade.status_code == 404

    def test_unassigned_question_hidden_from_every_mentor(
        self, node, teams, questions, running_game
    ):
        user = make_user(teams[0], "player-unasn")
        mentor_a = make_user(None, "mentor-a", staff=True)
        mentor_b = make_user(None, "mentor-b", staff=True)
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.refresh_from_db()
        assert occ.question.mentor_id is None
        submission = submit_answer(occ, user, body="42")

        client = APIClient()
        for mentor in (mentor_a, mentor_b):
            client.force_authenticate(user=mentor)
            listing = client.get("/api/submissions/")
            detail = client.get(f"/api/submissions/{submission.pk}/")
            assert all(row["id"] != submission.pk for row in listing.data)
            assert detail.status_code == 404

    def test_superuser_sees_every_submission(self, node, teams, questions, running_game):
        user = make_user(teams[0], "player-su")
        owner = make_user(None, "mentor-owner-su", staff=True)
        admin = make_user(None, "super-admin", staff=True)
        admin.is_superuser = True
        admin.save(update_fields=["is_superuser"])

        occ = occupy(node, teams[0])
        assign_question(occ)
        assign_to_mentor(occ, owner)
        submission = submit_answer(occ, user, body="42")

        client = APIClient()
        client.force_authenticate(user=admin)
        listing = client.get("/api/submissions/")
        detail = client.get(f"/api/submissions/{submission.pk}/")
        grade = client.post(
            f"/api/submissions/{submission.pk}/grade/", {"grade": 50}, format="json"
        )

        assert any(row["id"] == submission.pk for row in listing.data)
        assert detail.status_code == 200
        assert grade.status_code == 200

    def test_one_mentor_can_own_several_questions(self, node, teams, easy, running_game):
        mentor = make_user(None, "multi-mentor", staff=True)
        qs = [
            Question.objects.create(
                level=easy,
                code=f"mq{i}",
                title=f"Multi {i}",
                body="x",
                answer_type=AnswerType.TEXT,
                answer_key="k",
                is_active=True,
                mentor=mentor,
            )
            for i in range(2)
        ]
        user = make_user(teams[0], "multi-player")
        nodes = [
            Node.objects.create(board=Board.GIRLS, code=f"mn{i}", name=f"MN{i}", level=easy)
            for i in range(2)
        ]
        submissions = []
        for i, question in enumerate(qs):
            occ = occupy(nodes[i], teams[0])
            occ.question = question
            occ.question_assigned_at = timezone.now()
            occ.save(update_fields=["question", "question_assigned_at"])
            submissions.append(submit_answer(occ, user, body=f"ans{i}"))

        client = APIClient()
        client.force_authenticate(user=mentor)
        listing = client.get("/api/submissions/")
        ids = {row["id"] for row in listing.data}
        assert {s.pk for s in submissions} <= ids


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

    def test_mentor_without_staff_can_download_submission_file(self, node, teams, running_game):
        file_question = Question.objects.create(
            level=node.level,
            code="fq2",
            title="File Q",
            body="Upload",
            answer_type=AnswerType.FILE,
            is_active=True,
        )
        user = make_user(teams[0], "file-user-2")
        mentor = make_user(None, "mentor-nostaff")
        mentor.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Occupancy),
                codename="act_as_mentor",
            )
        )
        occ = occupy(node, teams[0])
        assign_question(occ)
        occ.question = file_question
        occ.save(update_fields=["question"])
        file_question.mentor = mentor
        file_question.save(update_fields=["mentor"])

        upload = SimpleUploadedFile("proof.png", b"hello", content_type="image/png")
        submission = submit_answer(occ, user, file=upload)

        client = APIClient()
        client.force_authenticate(user=mentor)
        response = client.get(f"/api/media/submissions/{submission.pk}/")
        assert response.status_code == 200

        detail = client.get(f"/api/submissions/{submission.pk}/")
        assert detail.status_code == 200
        assert detail.data["file_name"].endswith(".png")
