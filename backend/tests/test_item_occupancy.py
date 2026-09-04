"""Item-sourced occupancies must sit on the board without becoming attempts.

These rows are fixtures of a future item-use path. Nothing here spends inventory.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.boards import Board
from game.models import (
    AcquisitionSource,
    AnswerType,
    Edge,
    GameSettings,
    GameStatus,
    LevelConfig,
    Node,
    Occupancy,
    Question,
)
from game.services import claim_node, grade_attempt, is_reachable
from game.services.mentor import Conflict
from game.services.movement import expandable_node_ids
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
def hard():
    return LevelConfig.objects.get(level="hard")


@pytest.fixture
def easy():
    return LevelConfig.objects.get(level="easy")


def _assigned(**kwargs) -> dict:
    now = timezone.now()
    kwargs.setdefault("question_assigned_at", now)
    kwargs.setdefault("expires_at", now + timedelta(minutes=15))
    return kwargs


class TestItemFloorsStayPut:
    def test_grading_does_not_move_or_pay_an_item_floor(self, running_game, hard):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        item_team = Team.objects.create(board=Board.GIRLS, code="item", name="Item", balance=0)
        alpha = Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=0)
        bravo = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo", balance=0)

        item = Occupancy.objects.create(
            node=node,
            team=item_team,
            slot=1,
            floor=2,
            source=AcquisitionSource.ITEM,
        )
        alpha_occ = Occupancy.objects.create(node=node, team=alpha, slot=2, **_assigned())
        bravo_occ = Occupancy.objects.create(node=node, team=bravo, slot=3, **_assigned())

        grade_attempt(alpha_occ, 90)
        item.refresh_from_db()
        alpha_occ.refresh_from_db()
        item_team.refresh_from_db()

        assert Occupancy.objects.active().filter(pk=item.pk).exists()
        assert item.source == AcquisitionSource.ITEM
        assert item.floor == 2
        assert item.grade is None
        assert item_team.balance == 0
        assert alpha_occ.floor == 1

        grade_attempt(bravo_occ, 100)
        item.refresh_from_db()
        alpha_occ.refresh_from_db()
        bravo_occ.refresh_from_db()
        item_team.refresh_from_db()

        assert item.source == AcquisitionSource.ITEM
        assert item.floor == 2
        assert item.grade is None
        assert item_team.balance == 0
        assert {alpha_occ.floor, bravo_occ.floor} == {1, 3}
        assert bravo_occ.floor == 3
        assert alpha_occ.floor == 1


class TestItemReach:
    @pytest.fixture
    def graph(self, easy):
        spawn = LevelConfig.objects.get(level="spawn")
        start = Node.objects.create(board=Board.GIRLS, code=START_CODE, name="Start", level=spawn)
        e1 = Node.objects.create(board=Board.GIRLS, code="e1", name="Easy 1", level=easy)
        m1 = Node.objects.create(
            board=Board.GIRLS,
            code="m1",
            name="Medium 1",
            level=LevelConfig.objects.get(level="medium"),
        )
        far = Node.objects.create(board=Board.GIRLS, code="far", name="Far", level=easy)
        for a, b in ((start, e1), (e1, m1)):
            lower, upper = sorted((a, b), key=lambda node: node.pk)
            Edge.objects.create(a=lower, b=upper, directed=False)
        return {"start": start, "e1": e1, "m1": m1, "far": far}

    @pytest.fixture
    def questions(self, graph):
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
            for i in range(1, 3)
        ]

    def test_item_ownership_expands_reach(self, running_game, graph, questions):
        team = Team.objects.create(
            board=Board.GIRLS,
            code="alpha",
            name="Alpha",
            balance=500,
            color=color_for_start(START_CODE),
        )
        Occupancy.objects.create(
            node=graph["e1"],
            team=team,
            slot=1,
            floor=1,
            source=AcquisitionSource.ITEM,
        )

        held = expandable_node_ids(team)
        assert graph["e1"].pk in held
        assert is_reachable(graph["m1"], held)
        assert not is_reachable(graph["far"], held)

        neighbour = claim_node(team, graph["m1"])
        assert neighbour.node_id == graph["m1"].pk
        assert neighbour.source == AcquisitionSource.ATTEMPT

    def test_ungraded_attempt_does_not_expand_reach(self, running_game, graph):
        team = Team.objects.create(
            board=Board.GIRLS,
            code="alpha",
            name="Alpha",
            balance=500,
            color=color_for_start(START_CODE),
        )
        Occupancy.objects.create(node=graph["e1"], team=team, slot=1)

        held = expandable_node_ids(team)
        assert held == set()
        assert not is_reachable(graph["m1"], held)

    def test_claim_node_rejects_an_item_holding(self, running_game, graph, questions):
        team = Team.objects.create(
            board=Board.GIRLS,
            code="alpha",
            name="Alpha",
            balance=500,
            color=color_for_start(START_CODE),
        )
        holding = Occupancy.objects.create(
            node=graph["e1"],
            team=team,
            slot=1,
            floor=1,
            source=AcquisitionSource.ITEM,
        )
        before = (
            holding.floor,
            holding.source,
            holding.question_id,
            holding.question_assigned_at,
            holding.grade,
        )

        with pytest.raises(Conflict):
            claim_node(team, graph["e1"])

        holding.refresh_from_db()
        assert (
            holding.floor,
            holding.source,
            holding.question_id,
            holding.question_assigned_at,
            holding.grade,
        ) == before
        assert holding.question_id is None
        assert Occupancy.objects.active().filter(team=team, node=graph["e1"]).count() == 1
