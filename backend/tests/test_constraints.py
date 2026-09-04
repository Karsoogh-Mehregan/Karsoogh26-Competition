"""Every invariant here is enforced by the database, not by application code.

That matters because select_for_update() is a silent no-op on SQLite, so any
invariant resting on the lock protocol alone would be untested in development.
"""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from game.models import (
    AcquisitionSource,
    Edge,
    FloorReward,
    GameSettings,
    GradeMultiplier,
    LevelConfig,
    Node,
    Occupancy,
    _round_half_up,
)
from teams.models import Team

pytestmark = pytest.mark.django_db


@pytest.fixture
def hard():
    return LevelConfig.objects.get(level="hard")


@pytest.fixture
def easy():
    return LevelConfig.objects.get(level="easy")


@pytest.fixture
def node(hard):
    return Node.objects.create(code="h1", name="Hard 1", level=hard)


@pytest.fixture
def teams():
    return [Team.objects.create(code=f"t{i}", name=f"Team {i}") for i in range(5)]


def occupy(node, team, **kwargs):
    kwargs.setdefault("slot", 1)
    return Occupancy.objects.create(node=node, team=team, **kwargs)


class TestCapacity:
    def test_slot_caps_ungraded_occupancies(self, node, teams):
        """The bug `slot` exists to fix.

        Capacity is consumed at payment, when floor is still NULL, and NULLs are
        distinct in a unique index — so the floor constraint cannot see them.
        """
        for i, team in enumerate(teams[:3], start=1):
            occupy(node, team, slot=i)

        with pytest.raises(IntegrityError), transaction.atomic():
            occupy(node, teams[3], slot=4)  # slot_range: > MAX_CAPACITY

    def test_duplicate_active_slot_rejected(self, node, teams):
        occupy(node, teams[0], slot=1)
        with pytest.raises(IntegrityError), transaction.atomic():
            occupy(node, teams[1], slot=1)

    def test_released_slot_is_reusable(self, node, teams):
        first = occupy(node, teams[0], slot=1)
        first.released_at = timezone.now()
        first.release_reason = "zero_grade"
        first.save()
        occupy(node, teams[1], slot=1)  # must not raise
        assert Occupancy.objects.active().count() == 1

    def test_one_unit_per_team_per_node(self, node, teams):
        occupy(node, teams[0], slot=1)
        with pytest.raises(IntegrityError), transaction.atomic():
            occupy(node, teams[0], slot=2)

    def test_item_floors_may_stack_for_one_team(self, node, teams):
        occupy(node, teams[0], slot=1, floor=1, source=AcquisitionSource.ITEM)
        occupy(node, teams[0], slot=2, floor=2, source=AcquisitionSource.ITEM)
        assert Occupancy.objects.active().filter(team=teams[0], node=node).count() == 2


class TestOccupancyIntegrity:
    def test_grade_above_100_rejected(self, node, teams):
        with pytest.raises(IntegrityError), transaction.atomic():
            occupy(
                node,
                teams[0],
                grade=101,
                grade_multiplier=Decimal("1.000"),
                question_assigned_at=timezone.now(),
            )

    def test_graded_row_requires_assigned_at(self, node, teams):
        """Without this, the grade DESC / assigned_at ASC tiebreak is not total —
        and PostgreSQL sorts NULLs last in ASC while SQLite sorts them first."""
        with pytest.raises(IntegrityError), transaction.atomic():
            occupy(node, teams[0], grade=50, grade_multiplier=Decimal("0.500"))

    def test_graded_row_requires_multiplier(self, node, teams):
        with pytest.raises(IntegrityError), transaction.atomic():
            occupy(node, teams[0], grade=50, question_assigned_at=timezone.now())


class TestTeam:
    def test_negative_balance_rejected(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            Team.objects.create(code="broke", name="Broke", balance=-1)

    def test_draft_order_unique(self):
        Team.objects.create(code="a", name="A", draft_order=1)
        with pytest.raises(IntegrityError), transaction.atomic():
            Team.objects.create(code="b", name="B", draft_order=1)


class TestMap:
    def test_bridge_must_be_normalised(self, hard, node):
        other = Node.objects.create(code="h2", name="Hard 2", level=hard)
        low, high = sorted([node, other], key=lambda i: i.pk)
        Edge.objects.create(a=low, b=high)
        with pytest.raises(IntegrityError), transaction.atomic():
            Edge.objects.create(a=high, b=low)

    def test_node_code_unique(self, easy):
        Node.objects.create(code="dup", level=easy)
        with pytest.raises(IntegrityError), transaction.atomic():
            Node.objects.create(code="dup", level=easy)


class TestGameSettings:
    def test_singleton(self):
        GameSettings.load()
        with pytest.raises(IntegrityError), transaction.atomic():
            GameSettings.objects.create(pk=2)

    def test_load_is_idempotent(self):
        assert GameSettings.load().pk == GameSettings.load().pk == 1


class TestEconomy:
    """Values from the design doc's derived table."""

    @pytest.mark.parametrize(
        ("level", "floor", "points", "networth", "duel", "buyout"),
        [
            ("easy", 1, 100, 40, 200, 400),
            ("medium", 1, 200, 115, 360, 800),
            ("medium", 2, 250, 125, 450, 1000),
            ("hard", 1, 400, 270, 600, 1600),
            ("hard", 3, 500, 300, 750, 2000),
        ],
    )
    def test_seeded_costs(self, level, floor, points, networth, duel, buyout):
        fr = FloorReward.objects.select_related("level").get(level_id=level, floor=floor)
        assert (fr.points, fr.networth, fr.duel_cost, fr.buyout_cost) == (
            points,
            networth,
            duel,
            buyout,
        )

    def test_rounding_is_half_up_not_bankers(self):
        """round() would send 262.5 down and 187.5 up — inconsistent in a currency."""
        assert _round_half_up(Decimal("1.5") * 175) == 263
        assert _round_half_up(Decimal("1.5") * 125) == 188
        assert round(262.5) == 262  # the behaviour being avoided

    def test_grade_curve_is_a_step_function(self):
        assert GradeMultiplier.factor_for(100) == Decimal("1.000")
        assert GradeMultiplier.factor_for(50) == Decimal("0.500")
        assert GradeMultiplier.factor_for(99) == Decimal("0.500")  # floors to the 50 breakpoint
        assert GradeMultiplier.factor_for(0) == Decimal("0.000")

    def test_voice_note_example(self):
        """«اگه ۵۰ نمره رو گرفته باشن ۵۰ امتیاز اون رنک رو می‌گیرن» — 50 on a 400 floor gives 200."""
        fr = FloorReward.objects.get(level_id="hard", floor=1)
        assert _round_half_up(fr.points * GradeMultiplier.factor_for(50)) == 200
