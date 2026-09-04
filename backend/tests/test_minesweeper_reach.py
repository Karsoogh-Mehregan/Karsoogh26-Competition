"""A won Minesweeper toll expands graph reach without becoming an Occupancy."""

import pytest
from django.contrib.auth import get_user_model
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
from game.services.mentor import Conflict
from game.services.movement import (
    claim_node,
    claim_spawn,
    expandable_node_ids,
    is_reachable,
    team_can_access_node,
)
from minesweeper.models import (
    MinesweeperAttempt,
    MinesweeperDifficulty,
    MinesweeperSettings,
    MinesweeperStatus,
)
from minesweeper.services import create_attempt, create_game
from teams.models import Team
from teams.start_colors import color_for_start

pytestmark = pytest.mark.django_db
User = get_user_model()

UNREACHABLE = "این خانه از مسیر فعلی تیم در دسترس نیست."
START_CODE = "L1_0"


@pytest.fixture
def running_game():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture
def easy():
    return LevelConfig.objects.get(level="easy")


@pytest.fixture
def spawn():
    return LevelConfig.objects.get(level="spawn")


@pytest.fixture
def toll_level():
    return LevelConfig.objects.get(level="toll")


def _undirected(a: Node, b: Node) -> Edge:
    lower, upper = sorted((a, b), key=lambda node: node.pk)
    return Edge.objects.create(a=lower, b=upper, directed=False)


def _hold(team: Team, node: Node, **kwargs) -> Occupancy:
    kwargs.setdefault("slot", 1)
    grade = kwargs.get("grade")
    if grade is not None:
        kwargs.setdefault("question_assigned_at", timezone.now())
        kwargs.setdefault("grade_multiplier", GradeMultiplier.factor_for(grade))
    return Occupancy.objects.create(team=team, node=node, **kwargs)


def _attempt(team: Team, node: Node, *, status: str) -> MinesweeperAttempt:
    game = create_game(node, MinesweeperDifficulty.EASY)
    attempt = create_attempt(game, team)
    if status == MinesweeperStatus.IN_PROGRESS:
        return attempt
    attempt.status = status
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=["status", "finished_at"])
    return attempt


def _questions(level: LevelConfig, n: int = 4) -> None:
    for i in range(1, n + 1):
        Question.objects.create(
            level=level,
            code=f"q-{level.pk}-{i}",
            title=f"Q {i}",
            body="Body",
            answer_type=AnswerType.TEXT,
            answer_key="k",
        )


@pytest.fixture
def graph(easy, spawn, toll_level):
    """L3 -> toll -> ahead, and behind -> toll only."""
    home = Node.objects.create(board=Board.GIRLS, code="L3_0", name="L3", level=easy)
    toll = Node.objects.create(board=Board.GIRLS, code="C34_0", name="Toll", level=toll_level)
    ahead = Node.objects.create(board=Board.GIRLS, code="L4_0", name="L4", level=easy)
    behind = Node.objects.create(board=Board.GIRLS, code="behind", name="Behind", level=easy)
    isolated = Node.objects.create(board=Board.GIRLS, code="far", name="Far", level=easy)
    Edge.objects.create(a=home, b=toll, directed=True)
    Edge.objects.create(a=toll, b=ahead, directed=True)
    Edge.objects.create(a=behind, b=toll, directed=True)
    return {
        "home": home,
        "toll": toll,
        "ahead": ahead,
        "behind": behind,
        "isolated": isolated,
        "spawn": spawn,
        "easy": easy,
    }


@pytest.fixture
def alpha():
    return Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=500)


@pytest.fixture
def beta():
    return Team.objects.create(board=Board.GIRLS, code="beta", name="Beta", balance=500)


class TestExpandableSources:
    def test_graded_occupancy_still_expands(self, alpha, graph):
        neighbour = Node.objects.create(
            board=Board.GIRLS, code="n2", name="N2", level=graph["easy"]
        )
        _undirected(graph["home"], neighbour)
        _hold(alpha, graph["home"], grade=80)

        held = expandable_node_ids(alpha)
        assert graph["home"].pk in held
        assert is_reachable(neighbour, held)
        assert not is_reachable(graph["isolated"], held)

    def test_won_attempt_makes_the_toll_expandable_without_occupancy(self, alpha, graph):
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)

        held = expandable_node_ids(alpha)
        assert graph["toll"].pk in held
        assert Occupancy.objects.filter(node=graph["toll"]).count() == 0
        assert team_can_access_node(alpha, graph["toll"])
        assert team_can_access_node(alpha, graph["ahead"])
        assert not team_can_access_node(alpha, graph["behind"])

    def test_lost_attempt_does_not_expand(self, alpha, graph):
        _hold(alpha, graph["home"], grade=80)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.LOST)

        held = expandable_node_ids(alpha)
        assert graph["toll"].pk not in held
        assert team_can_access_node(alpha, graph["toll"])
        assert not team_can_access_node(alpha, graph["ahead"])

    def test_in_progress_attempt_does_not_expand(self, alpha, graph):
        _hold(alpha, graph["home"], grade=80)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.IN_PROGRESS)

        held = expandable_node_ids(alpha)
        assert graph["toll"].pk not in held
        assert not team_can_access_node(alpha, graph["ahead"])

    def test_another_teams_win_does_not_unlock_this_team(self, alpha, beta, graph):
        _hold(alpha, graph["home"], grade=80)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)

        assert graph["toll"].pk not in expandable_node_ids(beta)
        assert not team_can_access_node(beta, graph["toll"])
        assert not team_can_access_node(beta, graph["ahead"])

    def test_each_team_unlocks_independently(self, alpha, beta, graph):
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)
        _attempt(beta, graph["toll"], status=MinesweeperStatus.WON)

        assert graph["toll"].pk in expandable_node_ids(alpha)
        assert graph["toll"].pk in expandable_node_ids(beta)
        assert team_can_access_node(alpha, graph["ahead"])
        assert team_can_access_node(beta, graph["ahead"])
        assert Occupancy.objects.filter(node=graph["toll"]).count() == 0

    def test_multiple_wins_on_the_same_toll_are_stable(self, alpha, graph):
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.LOST)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)

        held = expandable_node_ids(alpha)
        assert held == {graph["toll"].pk}
        assert team_can_access_node(alpha, graph["ahead"])
        assert Occupancy.objects.filter(node=graph["toll"]).count() == 0


class TestDirectedReachAfterWin:
    def test_won_toll_opens_the_forward_node(self, running_game, alpha, graph):
        _questions(graph["easy"])
        _hold(alpha, graph["home"], grade=80)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)

        holding = claim_node(alpha, graph["ahead"])

        assert holding.node_id == graph["ahead"].pk
        assert Occupancy.objects.active().filter(node=graph["toll"]).count() == 0

    def test_won_toll_still_opens_ahead_after_houses_are_released(self, running_game, alpha, graph):
        _questions(graph["easy"])
        holding = _hold(alpha, graph["home"], grade=80)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)
        holding.released_at = timezone.now()
        holding.release_reason = "expired"
        holding.save(update_fields=["released_at", "release_reason"])

        claimed = claim_node(alpha, graph["ahead"])
        assert claimed.node_id == graph["ahead"].pk
        assert Occupancy.objects.active().filter(node=graph["toll"]).count() == 0

    def test_reverse_only_edge_does_not_open(self, running_game, alpha, graph):
        _questions(graph["easy"])
        _hold(alpha, graph["home"], grade=80)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)

        with pytest.raises(Conflict) as caught:
            claim_node(alpha, graph["behind"])
        assert "متصل" in str(caught.value)
        assert not Occupancy.objects.filter(node=graph["behind"]).exists()

    def test_other_team_cannot_claim_through_this_win(self, running_game, alpha, beta, graph):
        _questions(graph["easy"])
        _hold(alpha, graph["home"], grade=80)
        _hold(beta, graph["isolated"], grade=80)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)

        with pytest.raises(Conflict) as caught:
            claim_node(beta, graph["ahead"])
        assert "متصل" in str(caught.value)
        assert not Occupancy.objects.filter(node=graph["ahead"]).exists()


class TestExistingFlows:
    def test_claim_node_on_a_normal_house_is_unchanged(self, running_game, alpha, graph):
        neighbour = Node.objects.create(
            board=Board.GIRLS, code="e-next", name="Next", level=graph["easy"]
        )
        _undirected(graph["home"], neighbour)
        _questions(graph["easy"])
        _hold(alpha, graph["home"], grade=80)

        holding = claim_node(alpha, neighbour)
        assert holding.node_id == neighbour.pk
        assert holding.is_spawn is False

    def test_claim_spawn_is_unchanged(self, running_game, spawn):
        start = Node.objects.create(board=Board.GIRLS, code=START_CODE, name="Start", level=spawn)
        team = Team.objects.create(
            board=Board.GIRLS,
            code="spawned",
            name="Spawned",
            balance=400,
            color=color_for_start(START_CODE),
        )
        holding = claim_spawn(team, start)
        assert holding.is_spawn is True
        assert holding.node_id == start.pk
        assert Occupancy.objects.active().filter(team=team).count() == 1

    def test_ungraded_reservation_still_does_not_expand(self, running_game, alpha, graph):
        _questions(graph["easy"])
        _hold(alpha, graph["home"])

        with pytest.raises(Conflict) as caught:
            claim_node(alpha, graph["ahead"])
        assert "نمره" in str(caught.value)

    def test_a_toll_is_never_claimed_with_a_question(self, running_game, alpha, graph):
        """Whatever the reach, a gate is played, not answered — so it is refused
        before the reach rules are even consulted."""
        _questions(graph["easy"])
        _hold(alpha, graph["home"], grade=80)

        with pytest.raises(Conflict) as caught:
            claim_node(alpha, graph["toll"])
        assert "مین‌روب" in str(caught.value)


class TestMinesweeperEntryGate:
    @pytest.fixture
    def alpha_client(self, alpha):
        user = User.objects.create_user("alpha-user", password="pw", team=alpha)
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_reachable_configured_toll_can_issue_a_ticket(
        self, running_game, alpha, alpha_client, graph
    ):
        MinesweeperSettings.objects.create(
            node=graph["toll"], difficulty_id=MinesweeperDifficulty.EASY, enabled=True
        )
        _hold(alpha, graph["home"], grade=80)

        response = alpha_client.post(
            f"/api/minesweeper/nodes/{graph['toll'].code}/enter/", {}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["node"] == graph["toll"].code
        assert response.json()["entry"]

    def test_unreachable_configured_toll_cannot_be_entered(self, running_game, alpha_client, graph):
        MinesweeperSettings.objects.create(
            node=graph["toll"], difficulty_id=MinesweeperDifficulty.EASY, enabled=True
        )

        response = alpha_client.post(
            f"/api/minesweeper/nodes/{graph['toll'].code}/enter/", {}, format="json"
        )
        assert response.status_code == 409
        assert response.json() == {"detail": UNREACHABLE}

    def test_guessing_start_on_an_unreachable_toll_does_not_create_a_game(
        self, running_game, alpha_client, graph
    ):
        MinesweeperSettings.objects.create(
            node=graph["toll"], difficulty_id=MinesweeperDifficulty.EASY, enabled=True
        )

        response = alpha_client.post(
            f"/api/minesweeper/nodes/{graph['toll'].code}/start/",
            {"entry": "forged"},
            format="json",
        )
        assert response.status_code == 409
        assert response.json() == {"detail": UNREACHABLE}
        assert not MinesweeperAttempt.objects.exists()

    def test_won_toll_stays_enterable_after_houses_are_released(
        self, running_game, alpha, alpha_client, graph
    ):
        MinesweeperSettings.objects.create(
            node=graph["toll"], difficulty_id=MinesweeperDifficulty.EASY, enabled=True
        )
        holding = _hold(alpha, graph["home"], grade=80)
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)
        holding.released_at = timezone.now()
        holding.release_reason = "expired"
        holding.save(update_fields=["released_at", "release_reason"])

        response = alpha_client.post(
            f"/api/minesweeper/nodes/{graph['toll'].code}/enter/", {}, format="json"
        )
        assert response.status_code == 200


class TestClearedTollsPayload:
    def test_teams_list_includes_won_tolls_and_masks_them(self, running_game, alpha, beta, graph):
        _attempt(alpha, graph["toll"], status=MinesweeperStatus.WON)
        _attempt(beta, graph["toll"], status=MinesweeperStatus.WON)
        user = User.objects.create_user("alpha-user", password="pw", team=alpha)
        client = APIClient()
        client.force_authenticate(user)

        response = client.get("/api/teams/")
        assert response.status_code == 200
        by_code = {row["code"]: row for row in response.json()}
        assert by_code["alpha"]["cleared_tolls"] == [graph["toll"].code]
        assert by_code["beta"]["cleared_tolls"] == []
        assert by_code["alpha"]["holdings"] == []
        assert Occupancy.objects.filter(node=graph["toll"]).count() == 0
