"""Item usage services: consume inventory and grant source=item holdings."""

import pytest

from core.boards import Board
from game.models import (
    AcquisitionSource,
    Edge,
    FloorReward,
    GameSettings,
    GameStatus,
    Level,
    LevelConfig,
    Node,
    Occupancy,
    ReleaseReason,
)
from game.services import (
    claim_node,
    consume_item,
    is_reachable,
    use_fake_document,
    use_gel,
    use_gilari,
)
from game.services.events import BOARD_NODE_CLAIMED, BOARD_RELEASED
from game.services.mentor import Conflict
from game.services.movement import expandable_node_ids
from teams.models import ItemType, Team, TeamItem

pytestmark = pytest.mark.django_db


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


@pytest.fixture
def team():
    return Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=400)


def give(team, item_type, quantity=1) -> TeamItem:
    return TeamItem.objects.create(team=team, item_type=item_type, quantity=quantity)


def occupy(node, team, **kwargs) -> Occupancy:
    kwargs.setdefault("slot", 1)
    return Occupancy.objects.create(node=node, team=team, **kwargs)


def reward_floors(node) -> list[int]:
    return list(
        FloorReward.objects.filter(level_id=node.level_id)
        .order_by("floor")
        .values_list("floor", flat=True)
    )


def assert_gel_owns_every_reward(node, team, holdings=None) -> list[Occupancy]:
    floors = reward_floors(node)
    active = list(Occupancy.objects.active().filter(node=node).order_by("floor", "pk"))
    if holdings is not None:
        assert sorted(holding.floor for holding in holdings) == floors
    assert [occupancy.floor for occupancy in active] == floors
    assert {occupancy.team_id for occupancy in active} == {team.pk}
    assert {occupancy.source for occupancy in active} == {AcquisitionSource.ITEM}
    assert Occupancy.objects.active().exclude(team=team).filter(node=node).count() == 0
    return active


def test_consume_item_decrements_and_deletes_at_zero(team):
    give(team, ItemType.GEL, quantity=2)

    leftover = consume_item(team, ItemType.GEL)
    assert leftover is not None
    assert leftover.quantity == 1

    assert consume_item(team, ItemType.GEL) is None
    assert not TeamItem.objects.filter(team=team, item_type=ItemType.GEL).exists()


def test_consume_item_rejects_a_missing_stack(team):
    with pytest.raises(Conflict):
        consume_item(team, ItemType.GEL)


class TestFakeDocument:
    def test_grants_one_item_floor_on_an_empty_node(self, running_game, hard, team):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        give(team, ItemType.FAKE_DOCUMENT)

        holding = use_fake_document(team, node)

        assert holding.source == AcquisitionSource.ITEM
        assert holding.floor == 1
        assert holding.grade is None
        assert holding.grade_multiplier is None
        assert holding.question_id is None
        assert holding.question_assigned_at is None
        assert not TeamItem.objects.filter(team=team, item_type=ItemType.FAKE_DOCUMENT).exists()

    def test_takes_the_next_free_floor_when_the_node_is_partly_full(self, running_game, hard, team):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        other = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo")
        occupy(node, other, slot=1, floor=1, source=AcquisitionSource.ATTEMPT)
        give(team, ItemType.FAKE_DOCUMENT)

        holding = use_fake_document(team, node)

        assert holding.floor == 2
        assert holding.slot == 2
        assert Occupancy.objects.active().filter(node=node).count() == 2

    def test_evicts_an_owner_when_the_node_is_full(self, running_game, hard, team):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        occupants = []
        for slot, code in enumerate(("bravo", "charlie", "delta"), start=1):
            other = Team.objects.create(board=Board.GIRLS, code=code, name=code.title())
            occupants.append(
                occupy(node, other, slot=slot, floor=slot, source=AcquisitionSource.ATTEMPT)
            )
        give(team, ItemType.FAKE_DOCUMENT)

        holding = use_fake_document(team, node)

        assert holding.source == AcquisitionSource.ITEM
        assert holding.team_id == team.pk
        assert Occupancy.objects.active().filter(node=node).count() == 3
        assert Occupancy.objects.active().filter(node=node, team=team).count() == 1
        released = Occupancy.objects.filter(node=node, released_at__isnull=False)
        assert released.count() == 1
        assert released.get().release_reason == ReleaseReason.ITEM_TAKEOVER
        assert holding.floor == released.get().floor

    def test_rejects_spawn_and_toll(self, running_game, team):
        spawn = Node.objects.create(
            board=Board.GIRLS,
            code="s1",
            name="Spawn",
            level=LevelConfig.objects.get(level=Level.SPAWN),
        )
        toll = Node.objects.create(
            board=Board.GIRLS,
            code="t1",
            name="Toll",
            level=LevelConfig.objects.get(level=Level.TOLL),
        )
        give(team, ItemType.FAKE_DOCUMENT, quantity=2)

        with pytest.raises(Conflict):
            use_fake_document(team, spawn)
        with pytest.raises(Conflict):
            use_fake_document(team, toll)
        assert TeamItem.objects.get(team=team).quantity == 2

    def test_item_floor_expands_reach(self, running_game, easy, team):
        e1 = Node.objects.create(board=Board.GIRLS, code="e1", name="Easy 1", level=easy)
        neighbour = Node.objects.create(board=Board.GIRLS, code="e2", name="Easy 2", level=easy)
        far = Node.objects.create(board=Board.GIRLS, code="e3", name="Easy 3", level=easy)
        lower, upper = sorted((e1, neighbour), key=lambda node: node.pk)
        Edge.objects.create(a=lower, b=upper, directed=False)
        give(team, ItemType.FAKE_DOCUMENT)

        use_fake_document(team, e1)

        held = expandable_node_ids(team)
        assert e1.pk in held
        assert is_reachable(neighbour, held)
        assert not is_reachable(far, held)


class TestGel:
    @pytest.mark.parametrize("level_id", ["easy", "medium", "hard"])
    def test_owns_every_floor_reward_on_an_empty_node(self, running_game, team, level_id):
        level = LevelConfig.objects.get(level=level_id)
        node = Node.objects.create(
            board=Board.GIRLS, code=f"n-{level_id}", name=level_id, level=level
        )
        give(team, ItemType.GEL, quantity=2)

        holdings = use_gel(team, node)

        assert_gel_owns_every_reward(node, team, holdings)
        leftover = TeamItem.objects.get(team=team, item_type=ItemType.GEL)
        assert leftover.quantity == 1

    def test_does_not_invent_a_floor_missing_from_rewards(self, running_game, hard, team):
        FloorReward.objects.filter(level_id=hard.level, floor=3).delete()
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        give(team, ItemType.GEL)

        holdings = use_gel(team, node)

        floors = reward_floors(node)
        assert 3 not in floors
        assert_gel_owns_every_reward(node, team, holdings)
        assert Occupancy.objects.active().filter(node=node, floor=3).count() == 0

    def test_picks_up_an_extra_floor_reward(self, running_game, easy, team):
        FloorReward.objects.create(level_id=easy.level, floor=2, points=150)
        node = Node.objects.create(board=Board.GIRLS, code="e1", name="Easy 1", level=easy)
        give(team, ItemType.GEL)

        holdings = use_gel(team, node)

        assert reward_floors(node) == [1, 2]
        assert_gel_owns_every_reward(node, team, holdings)

    def test_clears_a_partly_occupied_node(self, running_game, hard, team):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        other = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo")
        occupy(node, other, slot=1, floor=1, source=AcquisitionSource.ITEM)
        previous = occupy(node, team, slot=2, floor=2)
        give(team, ItemType.GEL)

        holdings = use_gel(team, node)

        assert_gel_owns_every_reward(node, team, holdings)
        previous.refresh_from_db()
        assert previous.released_at is not None
        assert previous.release_reason == ReleaseReason.ITEM_TAKEOVER
        assert previous.pk not in {holding.pk for holding in holdings}

    def test_clears_a_full_node(self, running_game, hard, team):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        previous = [
            occupy(
                node,
                Team.objects.create(board=Board.GIRLS, code=code, name=code.title()),
                slot=slot,
                floor=slot,
                source=AcquisitionSource.ATTEMPT,
            )
            for slot, code in enumerate(("bravo", "charlie", "delta"), start=1)
        ]
        give(team, ItemType.GEL)

        use_gel(team, node)

        assert_gel_owns_every_reward(node, team)
        for occupancy in previous:
            occupancy.refresh_from_db()
            assert occupancy.released_at is not None
            assert occupancy.release_reason == ReleaseReason.ITEM_TAKEOVER

    def test_second_gel_replaces_previous_ownership(self, running_game, team):
        level = LevelConfig.objects.get(level="medium")
        node = Node.objects.create(board=Board.GIRLS, code="m1", name="Medium 1", level=level)
        give(team, ItemType.GEL, quantity=2)

        first = use_gel(team, node)
        second = use_gel(team, node)

        assert_gel_owns_every_reward(node, team, second)
        for occupancy in first:
            occupancy.refresh_from_db()
            assert occupancy.released_at is not None
        assert {holding.pk for holding in first}.isdisjoint({holding.pk for holding in second})
        assert not TeamItem.objects.filter(team=team, item_type=ItemType.GEL).exists()

    def test_other_team_cannot_claim_a_gelled_node(self, running_game, easy, team):
        level = LevelConfig.objects.get(level="medium")
        house = Node.objects.create(board=Board.GIRLS, code="m1", name="Medium 1", level=level)
        neighbour = Node.objects.create(board=Board.GIRLS, code="e1", name="Easy 1", level=easy)
        lower, upper = sorted((house, neighbour), key=lambda node: node.pk)
        Edge.objects.create(a=lower, b=upper, directed=False)
        other = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo", balance=400)
        occupy(neighbour, other, slot=1, floor=1, source=AcquisitionSource.ITEM)
        give(team, ItemType.GEL)

        use_gel(team, house)

        with pytest.raises(Conflict):
            claim_node(other, house)
        with pytest.raises(Conflict):
            claim_node(team, house)
        assert_gel_owns_every_reward(house, team)


class TestGilari:
    def test_consumes_without_touching_the_board(self, running_game, hard, team, monkeypatch):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        other = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo")
        existing = occupy(node, other, slot=1, floor=1)
        give(team, ItemType.GILARI_100)
        published = []
        monkeypatch.setattr(
            "game.services.items.publish_on_commit",
            lambda *args, **kwargs: published.append((args, kwargs)),
        )

        use_gilari(team)

        existing.refresh_from_db()
        assert existing.released_at is None
        assert Occupancy.objects.active().count() == 1
        assert not TeamItem.objects.filter(team=team).exists()
        assert published == []
        assert not Occupancy.objects.filter(team=team).exists()


def test_fake_document_and_gel_publish_board_hints(running_game, easy, team, monkeypatch):
    node = Node.objects.create(board=Board.GIRLS, code="e1", name="Easy 1", level=easy)
    give(team, ItemType.FAKE_DOCUMENT)
    give(team, ItemType.GEL)
    published = []
    monkeypatch.setattr(
        "game.services.items.publish_on_commit",
        lambda event, payload=None, **kwargs: published.append(event),
    )

    use_fake_document(team, node)
    assert BOARD_NODE_CLAIMED in published

    published.clear()
    use_gel(team, node)
    assert BOARD_RELEASED in published
    assert BOARD_NODE_CLAIMED in published
