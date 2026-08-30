"""assign-question is the move: it reserves a reachable node and starts the clock."""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
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
from teams.models import Team
from teams.start_colors import color_for_start

pytestmark = pytest.mark.django_db

START_CODE = "L1_0"


def claim_url(team: str, node: str) -> str:
    return reverse("game:assign-question", kwargs={"team_code": team, "node_code": node})


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
        code: Node.objects.create(code=code, name=code, level=levels[level])
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
        code="alpha", name="Alpha", balance=500, color=color_for_start(START_CODE)
    )


@pytest.fixture
def client_mentor(django_user_model):
    mentor = django_user_model.objects.create_user("mentor", password="conductor")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    client = APIClient()
    client.force_authenticate(mentor)
    return client


def hold(team: Team, node: Node, **kwargs) -> Occupancy:
    kwargs.setdefault("slot", 1)
    return Occupancy.objects.create(team=team, node=node, **kwargs)


class TestFirstMove:
    def test_start_node_is_reserved_and_handed_a_question(
        self, client_mentor, running_game, graph, questions, team
    ):
        response = client_mentor.post(claim_url("alpha", START_CODE))

        assert response.status_code == 200
        assert response.data["node"]["code"] == START_CODE
        assert response.data["slot"] == 1
        assert response.data["question_assigned_at"] is not None
        assert response.data["floor"] is None
        holding = Occupancy.objects.active().get(team=team)
        assert holding.is_spawn is True
        assert holding.question_id is not None

    def test_a_team_with_no_holdings_cannot_start_elsewhere(
        self, client_mentor, running_game, graph, questions, team
    ):
        response = client_mentor.post(claim_url("alpha", "e1"))

        assert response.status_code == 409
        assert not Occupancy.objects.filter(team=team).exists()

    def test_another_teams_start_node_is_refused(
        self, client_mentor, running_game, graph, questions, team
    ):
        node = Node.objects.create(
            code="L1_4", name="L1_4", level=LevelConfig.objects.get(level="spawn")
        )
        undirected(node, Node.objects.get(code="e1"))

        assert client_mentor.post(claim_url("alpha", "L1_4")).status_code == 409

    def test_colorless_team_cannot_move(self, client_mentor, running_game, graph, questions):
        Team.objects.create(code="bravo", name="Bravo", balance=500)
        assert client_mentor.post(claim_url("bravo", START_CODE)).status_code == 409


class TestAdjacency:
    def test_neighbour_of_a_held_node_is_reachable(
        self, client_mentor, running_game, graph, questions, team
    ):
        hold(team, graph[START_CODE], is_spawn=True)

        response = client_mentor.post(claim_url("alpha", "e1"))

        assert response.status_code == 200
        assert set(Occupancy.objects.active().values_list("node__code", flat=True)) == {
            START_CODE,
            "e1",
        }

    def test_disconnected_node_is_refused(
        self, client_mentor, running_game, graph, questions, team
    ):
        hold(team, graph[START_CODE], is_spawn=True)

        response = client_mentor.post(claim_url("alpha", "far"))

        assert response.status_code == 409
        assert not Occupancy.objects.filter(node__code="far").exists()

    def test_two_hops_away_is_refused(self, client_mentor, running_game, graph, questions, team):
        hold(team, graph[START_CODE], is_spawn=True)

        assert client_mentor.post(claim_url("alpha", "m1")).status_code == 409

    def test_released_holdings_do_not_extend_reach(
        self, client_mentor, running_game, graph, questions, team
    ):
        hold(team, graph[START_CODE], is_spawn=True)
        released = hold(team, graph["e1"], slot=2)
        released.released_at = released.entered_at
        released.release_reason = "expired"
        released.save(update_fields=["released_at", "release_reason"])

        assert client_mentor.post(claim_url("alpha", "m1")).status_code == 409

    def test_directed_edge_is_one_way(self, client_mentor, running_game, graph, questions, team):
        hold(team, graph["e1"])

        assert client_mentor.post(claim_url("alpha", "e2")).status_code == 200

    def test_directed_edge_is_refused_backwards(
        self, client_mentor, running_game, graph, questions, team
    ):
        hold(team, graph["e2"])

        assert client_mentor.post(claim_url("alpha", "e1")).status_code == 409


class TestSlotsAndCost:
    def test_entry_cost_is_charged_once(self, client_mentor, running_game, graph, questions, team):
        hold(team, graph[START_CODE], is_spawn=True)
        cost = LevelConfig.objects.get(level="easy").entry_cost

        assert client_mentor.post(claim_url("alpha", "e1")).status_code == 200
        team.refresh_from_db()
        assert team.balance == 500 - cost

        # Re-posting hits the already-assigned guard, not the wallet.
        assert client_mentor.post(claim_url("alpha", "e1")).status_code == 409
        team.refresh_from_db()
        assert team.balance == 500 - cost

    def test_a_poor_team_cannot_move(self, client_mentor, running_game, graph, questions, team):
        hold(team, graph[START_CODE], is_spawn=True)
        Team.objects.filter(pk=team.pk).update(balance=1)

        response = client_mentor.post(claim_url("alpha", "e1"))

        assert response.status_code == 409
        team.refresh_from_db()
        assert team.balance == 1

    def test_the_next_free_slot_is_taken(self, client_mentor, running_game, graph, questions, team):
        other = Team.objects.create(code="bravo", name="Bravo", balance=500)
        hold(other, graph["m1"], slot=1)
        hold(team, graph["e1"])

        response = client_mentor.post(claim_url("alpha", "m1"))

        assert response.status_code == 200
        assert response.data["slot"] == 2

    def test_a_full_node_is_refused(self, client_mentor, running_game, graph, questions, team):
        capacity = LevelConfig.objects.get(level="easy").capacity
        for slot in range(1, capacity + 1):
            filler = Team.objects.create(code=f"t{slot}", name=f"T{slot}", balance=0)
            hold(filler, graph["e3"], slot=slot)
        hold(team, graph["e1"])

        response = client_mentor.post(claim_url("alpha", "e3"))

        assert response.status_code == 409
        team.refresh_from_db()
        assert team.balance == 500


class TestGuards:
    def test_unknown_node_is_404(self, client_mentor, running_game, graph, questions, team):
        assert client_mentor.post(claim_url("alpha", "nowhere")).status_code == 404

    def test_unknown_team_is_404(self, client_mentor, running_game, graph, questions):
        assert client_mentor.post(claim_url("nobody", START_CODE)).status_code == 404

    def test_requires_a_running_game(self, client_mentor, graph, questions, team):
        assert client_mentor.post(claim_url("alpha", START_CODE)).status_code == 409

    def test_an_empty_question_bank_reserves_nothing(
        self, client_mentor, running_game, graph, team
    ):
        response = client_mentor.post(claim_url("alpha", START_CODE))

        assert response.status_code == 409
        assert not Occupancy.objects.filter(team=team).exists()

    def test_non_mentor_is_rejected(self, django_user_model, running_game, graph, questions, team):
        client = APIClient()
        client.force_authenticate(django_user_model.objects.create_user("player", password="x"))

        assert client.post(claim_url("alpha", START_CODE)).status_code == 403
