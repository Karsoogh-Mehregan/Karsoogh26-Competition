"""Mentor endpoints: authorization, state guards, and the tower/payout rule.

The economy numbers here are not free-standing: they fall out of the seeded curve
(GRADE_CURVE floors 90 and 70 to the 0.500 breakpoint, 100 to 1.000) and the seeded
rewards (hard = 400/450/500), the same table pinned by TestEconomy.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from game.models import (
    AnswerType,
    GameSettings,
    GameStatus,
    LevelConfig,
    Node,
    Occupancy,
    Question,
)
from teams.models import Team

pytestmark = pytest.mark.django_db

TEAM_CODES = ("alpha", "bravo", "charlie")


def action_url(action: str, team: str, node: str = "h1") -> str:
    return reverse(f"game:{action}", kwargs={"team_code": team, "node_code": node})


@pytest.fixture
def running_game():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture
def hard_node():
    return Node.objects.create(
        code="h1", name="Hard 1", level=LevelConfig.objects.get(level="hard")
    )


@pytest.fixture
def hard_questions(hard_node):
    """assign-question draws from the bank, so the hard level needs stock."""
    return [
        Question.objects.create(
            level=hard_node.level,
            code=f"hq{i}",
            title=f"Hard {i}",
            body=f"Body {i}",
            answer_type=AnswerType.TEXT,
            answer_key=f"key{i}",
            is_active=True,
        )
        for i in range(1, 4)
    ]


@pytest.fixture
def teams():
    return {code: Team.objects.create(code=code, name=code.title()) for code in TEAM_CODES}


@pytest.fixture
def holdings(hard_node, teams):
    """One holding per team, each already handed a question, staggered in time."""
    assigned = timezone.now() - timedelta(minutes=5)
    return {
        code: Occupancy.objects.create(
            node=hard_node,
            team=team,
            slot=slot,
            question_assigned_at=assigned + timedelta(seconds=slot),
            expires_at=assigned + timedelta(minutes=15),
        )
        for slot, (code, team) in enumerate(teams.items(), start=1)
    }


@pytest.fixture
def mentor(django_user_model):
    user = django_user_model.objects.create_user("mentor", password="conductor")
    user.groups.add(Group.objects.get(name="Mentors"))
    return user


@pytest.fixture
def client_mentor(mentor):
    client = APIClient()
    client.force_authenticate(mentor)
    return client


def balances():
    return dict(Team.objects.values_list("code", "balance"))


def floors(node):
    return dict(Occupancy.objects.active().filter(node=node).values_list("team__code", "floor"))


class TestPermission:
    def test_anonymous_is_rejected(self, hard_node, holdings):
        response = APIClient().post(action_url("grade", "alpha"), {"grade": 50}, format="json")
        assert response.status_code == 403

    def test_authenticated_non_mentor_is_rejected(self, django_user_model, holdings):
        client = APIClient()
        client.force_authenticate(django_user_model.objects.create_user("player", password="x"))
        response = client.post(action_url("grade", "alpha"), {"grade": 50}, format="json")
        assert response.status_code == 403

    def test_superuser_passes_without_the_group(self, django_user_model, running_game, holdings):
        client = APIClient()
        client.force_authenticate(django_user_model.objects.create_superuser("root", password="x"))
        response = client.post(action_url("grade", "alpha"), {"grade": 50}, format="json")
        assert response.status_code == 200


class TestLookup:
    def test_unknown_team_is_404(self, client_mentor, holdings):
        assert client_mentor.post(action_url("assign-question", "nobody")).status_code == 404

    def test_team_without_a_holding_on_that_node_is_404(
        self, client_mentor, running_game, hard_node, teams
    ):
        """grade/release address an existing holding; assign-question creates one instead."""
        other = Node.objects.create(
            code="h2", name="Hard 2", level=LevelConfig.objects.get(level="hard")
        )
        Occupancy.objects.create(node=other, team=teams["alpha"], slot=1)
        response = client_mentor.post(action_url("grade", "alpha"), {"grade": 50}, format="json")
        assert response.status_code == 404

    def test_released_holding_is_404(self, client_mentor, holdings, running_game):
        holding = holdings["alpha"]
        holding.released_at = timezone.now()
        holding.release_reason = "expired"
        holding.save()
        assert client_mentor.post(action_url("grade", "alpha"), {"grade": 50}).status_code == 404


class TestAssignQuestion:
    @pytest.fixture
    def fresh(self, hard_node, teams):
        return Occupancy.objects.create(node=hard_node, team=teams["alpha"], slot=1)

    def test_starts_the_clock_from_the_configured_ttl(
        self, client_mentor, running_game, hard_questions, fresh
    ):
        response = client_mentor.post(action_url("assign-question", "alpha"))
        assert response.status_code == 200

        fresh.refresh_from_db()
        assert fresh.question_assigned_at is not None
        assert fresh.expires_at - fresh.question_assigned_at == timedelta(
            minutes=running_game.attempt_ttl_minutes
        )
        assert response.data["is_expired"] is False

    def test_second_assignment_conflicts(self, client_mentor, running_game, hard_questions, fresh):
        client_mentor.post(action_url("assign-question", "alpha"))
        first = Occupancy.objects.get(pk=fresh.pk).question_assigned_at

        response = client_mentor.post(action_url("assign-question", "alpha"))
        assert response.status_code == 409
        assert Occupancy.objects.get(pk=fresh.pk).question_assigned_at == first

    def test_requires_a_running_game(self, client_mentor, fresh):
        assert client_mentor.post(action_url("assign-question", "alpha")).status_code == 409


class TestGrade:
    def test_rejects_a_grade_above_100(self, client_mentor, running_game, holdings):
        response = client_mentor.post(action_url("grade", "alpha"), {"grade": 101}, format="json")
        assert response.status_code == 400

    def test_requires_an_assigned_question(self, client_mentor, running_game, hard_node, teams):
        Occupancy.objects.create(node=hard_node, team=teams["alpha"], slot=1)
        response = client_mentor.post(action_url("grade", "alpha"), {"grade": 50}, format="json")
        assert response.status_code == 409

    def test_regrading_conflicts(self, client_mentor, running_game, holdings):
        client_mentor.post(action_url("grade", "alpha"), {"grade": 70}, format="json")
        response = client_mentor.post(action_url("grade", "alpha"), {"grade": 90}, format="json")
        assert response.status_code == 409
        assert Occupancy.objects.get(pk=holdings["alpha"].pk).grade == 70

    def test_requires_a_running_game(self, client_mentor, holdings):
        response = client_mentor.post(action_url("grade", "alpha"), {"grade": 50}, format="json")
        assert response.status_code == 409

    def test_tower_grows_upward_and_pays_each_promotion(
        self, client_mentor, running_game, hard_node, holdings
    ):
        """The worked example: the tower fills from floor 1, best grade on top.

        Every seeded grade here floors to the 0.500 multiplier except 100, which is
        1.000 — so bravo's 90 on floor 1 is worth 200, not 400.
        """
        client_mentor.post(action_url("grade", "bravo"), {"grade": 90}, format="json")
        assert floors(hard_node) == {"alpha": None, "bravo": 1, "charlie": None}
        assert balances() == {"alpha": 0, "bravo": 200, "charlie": 0}

        # A weaker grade slides in underneath, pushing bravo up a floor and paying the
        # difference: 450*0.5 - 400*0.5 = 25.
        client_mentor.post(action_url("grade", "alpha"), {"grade": 70}, format="json")
        assert floors(hard_node) == {"alpha": 1, "bravo": 2, "charlie": None}
        assert balances() == {"alpha": 200, "bravo": 225, "charlie": 0}

        # The best grade takes the new top floor; nobody below it moves or is charged.
        response = client_mentor.post(action_url("grade", "charlie"), {"grade": 100}, format="json")
        assert response.status_code == 200
        assert floors(hard_node) == {"alpha": 1, "bravo": 2, "charlie": 3}
        assert balances() == {"alpha": 200, "bravo": 225, "charlie": 500}
        assert response.data["points"] == 500
        assert response.data["team"]["balance"] == 500

    def test_no_floor_is_ever_lost(self, client_mentor, running_game, hard_node, holdings):
        """Grades arriving worst-first is the case that would demote, if anything could."""
        for code, grade in (("charlie", 100), ("bravo", 90), ("alpha", 70)):
            client_mentor.post(action_url("grade", code), {"grade": grade}, format="json")

        assert floors(hard_node) == {"alpha": 1, "bravo": 2, "charlie": 3}
        assert balances() == {"alpha": 200, "bravo": 225, "charlie": 500}

    def test_zero_grade_claims_no_floor(self, client_mentor, running_game, hard_node, holdings):
        response = client_mentor.post(action_url("grade", "alpha"), {"grade": 0}, format="json")

        assert response.status_code == 200
        assert response.data["floor"] is None
        assert response.data["points"] == 0
        assert Occupancy.objects.get(pk=holdings["alpha"].pk).grade == 0
        assert balances()["alpha"] == 0

    def test_grading_past_capacity_conflicts_and_rolls_back(
        self, client_mentor, running_game, teams
    ):
        """medium holds 2, but occ_slot_range allows 3 — only the service stops the third."""
        node = Node.objects.create(
            code="m1", name="Medium 1", level=LevelConfig.objects.get(level="medium")
        )
        assigned = timezone.now()
        for slot, team in enumerate(teams.values(), start=1):
            Occupancy.objects.create(node=node, team=team, slot=slot, question_assigned_at=assigned)

        for code, grade in (("alpha", 100), ("bravo", 90)):
            assert (
                client_mentor.post(
                    action_url("grade", code, node="m1"), {"grade": grade}, format="json"
                ).status_code
                == 200
            )

        response = client_mentor.post(
            action_url("grade", "charlie", node="m1"), {"grade": 80}, format="json"
        )
        assert response.status_code == 409
        charlie = Occupancy.objects.get(node=node, team__code="charlie")
        assert charlie.grade is None and charlie.grade_multiplier is None


class TestRelease:
    def test_frees_the_slot_without_touching_money(self, client_mentor, holdings, hard_node):
        response = client_mentor.post(
            action_url("release", "alpha"), {"reason": "expired"}, format="json"
        )

        assert response.status_code == 200
        holding = Occupancy.objects.get(pk=holdings["alpha"].pk)
        assert holding.released_at is not None
        assert holding.release_reason == "expired"
        assert balances()["alpha"] == 0
        # The slot is now reusable: the partial unique index only sees active rows.
        Occupancy.objects.create(
            node=hard_node, team=Team.objects.create(code="d", name="D"), slot=1
        )

    @pytest.mark.parametrize("reason", ["duel_lost", "bought_out"])
    def test_transfer_reasons_are_rejected(self, client_mentor, holdings, reason):
        response = client_mentor.post(
            action_url("release", "alpha"), {"reason": reason}, format="json"
        )
        assert response.status_code == 400

    def test_releasing_twice_conflicts(self, client_mentor, holdings):
        client_mentor.post(action_url("release", "alpha"), {"reason": "expired"}, format="json")
        response = client_mentor.post(
            action_url("release", "alpha"), {"reason": "expired"}, format="json"
        )
        assert response.status_code == 404  # no active holding left to address

    def test_cannot_release_a_floor_holder(self, client_mentor, running_game, holdings):
        """Releasing a captured floor would leave a hole, which the payout rule forbids."""
        client_mentor.post(action_url("grade", "alpha"), {"grade": 90}, format="json")

        response = client_mentor.post(
            action_url("release", "alpha"), {"reason": "zero_grade"}, format="json"
        )
        assert response.status_code == 409
        assert Occupancy.objects.get(pk=holdings["alpha"].pk).released_at is None

    def test_zero_graded_holding_is_releasable(self, client_mentor, running_game, holdings):
        client_mentor.post(action_url("grade", "alpha"), {"grade": 0}, format="json")

        response = client_mentor.post(
            action_url("release", "alpha"), {"reason": "zero_grade"}, format="json"
        )
        assert response.status_code == 200
        assert Occupancy.objects.get(pk=holdings["alpha"].pk).released_at is not None

    def test_release_is_allowed_while_paused(self, client_mentor, holdings):
        settings = GameSettings.load()
        settings.status = GameStatus.PAUSED
        settings.save(update_fields=["status"])

        response = client_mentor.post(
            action_url("release", "alpha"), {"reason": "expired"}, format="json"
        )
        assert response.status_code == 200
