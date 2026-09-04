"""assign-question is the move: it reserves a reachable node and starts the clock."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.boards import Board
from game.models import (
    AnswerType,
    Edge,
    GameSettings,
    GameStatus,
    GradeMultiplier,
    LevelConfig,
    Node,
    Occupancy,
    Question,
)
from game.services import assign_question, open_attempt_count
from teams.models import Team
from teams.start_colors import color_for_start

pytestmark = pytest.mark.django_db

START_CODE = "L1_0"


def claim_url(team: str, node: str) -> str:
    return reverse("game:assign-question", kwargs={"team_code": team, "node_code": node})


def client_for(django_user_model, team: Team) -> APIClient:
    user = django_user_model.objects.create_user(f"user-{team.code}", password="x", team=team)
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def running_game():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture
def nodes():
    levels = {row.pk: row for row in LevelConfig.objects.all()}
    codes = {
        START_CODE: "spawn",
        "e1": "easy",
        "e2": "easy",
        "e3": "easy",
        "m1": "medium",
        "far": "easy",
    }
    return {
        code: Node.objects.create(board=Board.GIRLS, code=code, name=code, level=levels[level])
        for code, level in codes.items()
    }


def undirected(a: Node, b: Node) -> Edge:
    lower, upper = sorted((a, b), key=lambda node: node.pk)
    return Edge.objects.create(a=lower, b=upper, directed=False)


@pytest.fixture
def graph(nodes):
    """L1_0 <-> e1 <-> m1, e1 -> e2 one-way, e3 undirected off e1. `far` is isolated."""
    undirected(nodes[START_CODE], nodes["e1"])
    undirected(nodes["e1"], nodes["m1"])
    undirected(nodes["e1"], nodes["e3"])
    Edge.objects.create(a=nodes["e1"], b=nodes["e2"], directed=True)
    return nodes


@pytest.fixture
def questions(nodes):
    return [
        Question.objects.create(
            level=level,
            code=f"q-{level.pk}-{i}",
            title=f"Q {level.pk} {i}",
            body="Body",
            answer_type=AnswerType.TEXT,
            answer_key="k",
        )
        for level in LevelConfig.objects.all()
        for i in range(1, 5)
    ]


@pytest.fixture
def team():
    return Team.objects.create(
        board=Board.GIRLS,
        code="alpha",
        name="Alpha",
        balance=500,
        color=color_for_start(START_CODE),
    )


@pytest.fixture
def client_team(django_user_model, team):
    return client_for(django_user_model, team)


def hold(team: Team, node: Node, **kwargs) -> Occupancy:
    kwargs.setdefault("slot", 1)
    grade = kwargs.get("grade")
    if grade is not None:
        kwargs.setdefault("question_assigned_at", timezone.now())
        kwargs.setdefault("grade_multiplier", GradeMultiplier.factor_for(grade))
    return Occupancy.objects.create(team=team, node=node, **kwargs)


class TestFirstMove:
    def test_start_node_is_reserved_and_handed_a_question(
        self, client_team, running_game, graph, questions, team
    ):
        response = client_team.post(claim_url("alpha", START_CODE))

        assert response.status_code == 200
        assert response.data["node"]["code"] == START_CODE
        assert response.data["slot"] == 1
        assert response.data["question_assigned_at"] is not None
        assert response.data["floor"] is None
        holding = Occupancy.objects.active().get(team=team)
        assert holding.is_spawn is True
        assert holding.source == "attempt"
        assert holding.question_id is not None

    def test_a_team_with_no_holdings_cannot_start_elsewhere(
        self, client_team, running_game, graph, questions, team
    ):
        response = client_team.post(claim_url("alpha", "e1"))

        assert response.status_code == 409
        assert not Occupancy.objects.filter(team=team).exists()

    def test_another_teams_start_node_is_refused(
        self, client_team, running_game, graph, questions, team
    ):
        node = Node.objects.create(
            board=Board.GIRLS,
            code="L1_4",
            name="L1_4",
            level=LevelConfig.objects.get(level="spawn"),
        )
        undirected(node, Node.objects.get(code="e1"))

        assert client_team.post(claim_url("alpha", "L1_4")).status_code == 409

    def test_colorless_team_cannot_move(self, django_user_model, running_game, graph, questions):
        bravo = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo", balance=500)
        client = client_for(django_user_model, bravo)

        assert client.post(claim_url("bravo", START_CODE)).status_code == 409


class TestAdjacency:
    def test_neighbour_of_a_held_node_is_reachable(
        self, client_team, running_game, graph, questions, team
    ):
        hold(team, graph[START_CODE], is_spawn=True)

        response = client_team.post(claim_url("alpha", "e1"))

        assert response.status_code == 200
        assert set(Occupancy.objects.active().values_list("node__code", flat=True)) == {
            START_CODE,
            "e1",
        }

    def test_disconnected_node_is_refused(self, client_team, running_game, graph, questions, team):
        hold(team, graph[START_CODE], is_spawn=True)

        response = client_team.post(claim_url("alpha", "far"))

        assert response.status_code == 409
        assert not Occupancy.objects.filter(node__code="far").exists()

    def test_two_hops_away_is_refused(self, client_team, running_game, graph, questions, team):
        hold(team, graph[START_CODE], is_spawn=True)

        assert client_team.post(claim_url("alpha", "m1")).status_code == 409

    def test_released_holdings_do_not_extend_reach(
        self, client_team, running_game, graph, questions, team
    ):
        hold(team, graph[START_CODE], is_spawn=True)
        released = hold(team, graph["e1"], slot=2)
        released.released_at = released.entered_at
        released.release_reason = "expired"
        released.save(update_fields=["released_at", "release_reason"])

        assert client_team.post(claim_url("alpha", "m1")).status_code == 409

    def test_directed_edge_is_one_way(self, client_team, running_game, graph, questions, team):
        hold(team, graph["e1"], grade=80)

        assert client_team.post(claim_url("alpha", "e2")).status_code == 200

    def test_directed_edge_is_refused_backwards(
        self, client_team, running_game, graph, questions, team
    ):
        hold(team, graph["e2"], grade=80)

        assert client_team.post(claim_url("alpha", "e1")).status_code == 409

    def test_an_ungraded_reservation_does_not_extend_reach(
        self, client_team, running_game, graph, questions, team
    ):
        hold(team, graph["e1"])

        response = client_team.post(claim_url("alpha", "m1"))

        assert response.status_code == 409
        assert "نمره" in response.json()["detail"]
        assert not Occupancy.objects.filter(node__code="m1").exists()


class TestSlotsAndCost:
    def test_entry_cost_is_charged_once(self, client_team, running_game, graph, questions, team):
        hold(team, graph[START_CODE], is_spawn=True)
        cost = LevelConfig.objects.get(level="easy").entry_cost

        assert client_team.post(claim_url("alpha", "e1")).status_code == 200
        team.refresh_from_db()
        assert team.balance == 500 - cost

        # Re-posting hits the already-assigned guard, not the wallet.
        assert client_team.post(claim_url("alpha", "e1")).status_code == 409
        team.refresh_from_db()
        assert team.balance == 500 - cost

    def test_a_poor_team_cannot_move(self, client_team, running_game, graph, questions, team):
        hold(team, graph[START_CODE], is_spawn=True)
        Team.objects.filter(pk=team.pk).update(balance=1)

        response = client_team.post(claim_url("alpha", "e1"))

        assert response.status_code == 409
        team.refresh_from_db()
        assert team.balance == 1

    def test_the_next_free_slot_is_taken(self, client_team, running_game, graph, questions, team):
        other = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo", balance=500)
        hold(other, graph["m1"], slot=1)
        hold(team, graph["e1"], grade=80)

        response = client_team.post(claim_url("alpha", "m1"))

        assert response.status_code == 200
        assert response.data["slot"] == 2

    def test_a_full_node_is_refused(self, client_team, running_game, graph, questions, team):
        capacity = LevelConfig.objects.get(level="easy").capacity
        for slot in range(1, capacity + 1):
            filler = Team.objects.create(
                board=Board.GIRLS, code=f"t{slot}", name=f"T{slot}", balance=0
            )
            hold(filler, graph["e3"], slot=slot)
        hold(team, graph["e1"], grade=80)

        response = client_team.post(claim_url("alpha", "e3"))

        assert response.status_code == 409
        team.refresh_from_db()
        assert team.balance == 500

    def test_an_expired_reservation_frees_the_slot(
        self, client_team, running_game, graph, questions, team
    ):
        hold(team, graph[START_CODE], is_spawn=True)
        occ = hold(team, graph["e1"])
        assign_question(occ)
        occ.expires_at = timezone.now() - timedelta(minutes=1)
        occ.save(update_fields=["expires_at"])

        response = client_team.post(claim_url("alpha", "e1"))

        assert response.status_code == 200
        occ.refresh_from_db()
        assert occ.released_at is not None
        assert Occupancy.objects.active().filter(team=team, node=graph["e1"]).exists()


class TestGuards:
    def test_unknown_node_is_404(self, client_team, running_game, graph, questions, team):
        assert client_team.post(claim_url("alpha", "nowhere")).status_code == 404

    def test_another_teams_code_is_403(self, client_team, running_game, graph, questions, team):
        Team.objects.create(board=Board.GIRLS, code="nobody", name="Nobody", balance=500)
        assert client_team.post(claim_url("nobody", START_CODE)).status_code == 403

    def test_requires_a_running_game(self, client_team, graph, questions, team):
        assert client_team.post(claim_url("alpha", START_CODE)).status_code == 403

    def test_an_empty_question_bank_reserves_nothing(self, client_team, running_game, graph, team):
        response = client_team.post(claim_url("alpha", START_CODE))

        assert response.status_code == 409
        assert not Occupancy.objects.filter(team=team).exists()

    def test_user_without_team_is_rejected(
        self, django_user_model, running_game, graph, questions, team
    ):
        client = APIClient()
        client.force_authenticate(django_user_model.objects.create_user("player", password="x"))

        assert client.post(claim_url("alpha", START_CODE)).status_code == 403

    def test_mentor_cannot_move_for_a_team(
        self, django_user_model, running_game, graph, questions, team
    ):
        mentor = django_user_model.objects.create_user("mentor", password="x")
        mentor.groups.add(Group.objects.get(name="Mentors"))
        client = APIClient()
        client.force_authenticate(mentor)

        assert client.post(claim_url("alpha", START_CODE)).status_code == 403


class TestOpenAttemptCap:
    """A team may hoard only `max_open_attempts` unanswered questions at a time."""

    @pytest.fixture
    def forked_start(self, graph):
        """e3 hangs off the spawn as well, so a third move is reachable at all."""
        undirected(graph[START_CODE], graph["e3"])
        return graph

    def submit_url(self, holding: Occupancy) -> str:
        return reverse("game:occupancy-submit", kwargs={"pk": holding.pk})

    def test_a_third_open_question_is_refused(
        self, client_team, running_game, forked_start, questions, team
    ):
        assert client_team.post(claim_url("alpha", START_CODE)).status_code == 200
        assert client_team.post(claim_url("alpha", "e1")).status_code == 200
        team.refresh_from_db()
        balance = team.balance

        response = client_team.post(claim_url("alpha", "e3"))

        assert response.status_code == 409
        assert not Occupancy.objects.filter(team=team, node__code="e3").exists()
        team.refresh_from_db()
        assert team.balance == balance

    def test_an_answered_question_stops_counting(
        self, client_team, running_game, forked_start, questions, team
    ):
        client_team.post(claim_url("alpha", START_CODE))
        client_team.post(claim_url("alpha", "e1"))
        spawn = Occupancy.objects.active().get(team=team, node__code=START_CODE)

        assert client_team.post(self.submit_url(spawn), {"body": "answer"}).status_code == 201
        assert client_team.post(claim_url("alpha", "e3")).status_code == 200

    def test_an_ungraded_submission_still_does_not_count(
        self, client_team, running_game, forked_start, questions, team
    ):
        """The cap is about hoarding, not about grading: the mentor is not the gate."""
        client_team.post(claim_url("alpha", START_CODE))
        client_team.post(claim_url("alpha", "e1"))
        spawn = Occupancy.objects.active().get(team=team, node__code=START_CODE)
        client_team.post(self.submit_url(spawn), {"body": "answer"})

        spawn.refresh_from_db()
        assert spawn.grade is None
        assert open_attempt_count(team) == 1

    def test_an_expired_attempt_stops_counting(
        self, client_team, running_game, forked_start, questions, team
    ):
        client_team.post(claim_url("alpha", START_CODE))
        client_team.post(claim_url("alpha", "e1"))
        Occupancy.objects.active().filter(team=team, node__code="e1").update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        assert client_team.post(claim_url("alpha", "e3")).status_code == 200

    def test_zero_turns_the_cap_off(self, client_team, running_game, forked_start, questions, team):
        running_game.max_open_attempts = 0
        running_game.save(update_fields=["max_open_attempts"])

        client_team.post(claim_url("alpha", START_CODE))
        client_team.post(claim_url("alpha", "e1"))

        assert client_team.post(claim_url("alpha", "e3")).status_code == 200
        assert open_attempt_count(team) == 3

    def test_granted_seats_do_not_count(self, running_game, forked_start, questions, team):
        """An item takeover or a duel win carries no question, so it is not hoarding."""
        hold(team, forked_start["m1"], source="duel", floor=1)

        assert open_attempt_count(team) == 0
