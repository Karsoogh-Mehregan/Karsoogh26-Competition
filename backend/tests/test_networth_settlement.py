"""The end-of-game networth settlement.

`FloorReward.networth` is the one price no live path reads: it is what a floor
is worth once the game is over. `settle_networth` pays it, once per team.
"""

import pytest

from core.boards import Board
from game.models import FloorReward, LevelConfig, Node, Occupancy
from game.services.networth import plan_settlement, settle_networth
from teams.models import BalanceEvent, BalanceReason, Team

pytestmark = pytest.mark.django_db


@pytest.fixture
def levels():
    return {row.pk: row for row in LevelConfig.objects.all()}


@pytest.fixture
def house(levels):
    return Node.objects.create(
        board=Board.GIRLS, code="H1", name="North Tower", level=levels["hard"]
    )


@pytest.fixture
def team():
    return Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=100)


def networth(level: str, floor: int) -> int:
    return FloorReward.objects.get(level_id=level, floor=floor).networth


def test_a_held_floor_pays_its_networth(house, team):
    Occupancy.objects.create(node=house, team=team, slot=1, floor=2)

    settle_networth()

    team.refresh_from_db()
    assert team.balance == 100 + networth("hard", 2)
    event = BalanceEvent.objects.get(team=team, reason=BalanceReason.NETWORTH)
    assert event.delta == networth("hard", 2)


def test_floors_add_up(house, levels, team):
    other = Node.objects.create(board=Board.GIRLS, code="H2", name="South", level=levels["easy"])
    Occupancy.objects.create(node=house, team=team, slot=1, floor=3)
    Occupancy.objects.create(node=other, team=team, slot=1, floor=1)

    settle_networth()

    team.refresh_from_db()
    assert team.balance == 100 + networth("hard", 3) + networth("easy", 1)


def test_a_reservation_pays_nothing(house, team):
    Occupancy.objects.create(node=house, team=team, slot=1, floor=None)

    assert settle_networth() == []
    team.refresh_from_db()
    assert team.balance == 100


def test_a_released_floor_pays_nothing(house, team):
    from django.utils import timezone

    Occupancy.objects.create(node=house, team=team, slot=1, floor=2, released_at=timezone.now())

    assert settle_networth() == []
    team.refresh_from_db()
    assert team.balance == 100


def test_a_second_run_pays_nothing(house, team):
    Occupancy.objects.create(node=house, team=team, slot=1, floor=2)

    settle_networth()
    settle_networth()

    team.refresh_from_db()
    assert team.balance == 100 + networth("hard", 2)
    assert BalanceEvent.objects.filter(team=team, reason=BalanceReason.NETWORTH).count() == 1


def test_board_scopes_the_settlement(house, levels, team):
    boys_node = Node.objects.create(
        board=Board.BOYS, code="H1", name="North Tower", level=levels["hard"]
    )
    boys = Team.objects.create(board=Board.BOYS, code="beta", name="Beta", balance=100)
    Occupancy.objects.create(node=house, team=team, slot=1, floor=2)
    Occupancy.objects.create(node=boys_node, team=boys, slot=1, floor=2)

    settle_networth(Board.GIRLS)

    team.refresh_from_db()
    boys.refresh_from_db()
    assert team.balance == 100 + networth("hard", 2)
    assert boys.balance == 100


def test_the_plan_reports_without_paying(house, team):
    Occupancy.objects.create(node=house, team=team, slot=1, floor=2)

    entry = next(row for row in plan_settlement() if row.team == team)

    assert (entry.amount, entry.floors, entry.already_settled) == (
        networth("hard", 2),
        1,
        False,
    )
    team.refresh_from_db()
    assert team.balance == 100
