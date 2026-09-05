"""Item usage services: consume inventory, grant fake-document floors, lock houses with gel."""

import pytest

from core.boards import Board
from game.models import (
    AcquisitionSource,
    Edge,
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
    claim_spawn,
    consume_item,
    is_reachable,
    use_fake_document,
    use_gel,
    use_gilari,
)
from game.services.events import BOARD_GELLED, BOARD_NODE_CLAIMED, BOARD_RELEASED
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
    def test_empties_and_locks_an_empty_node(self, running_game, hard, team):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        give(team, ItemType.GEL, quantity=2)

        released = use_gel(team, node)

        node.refresh_from_db()
        assert released == []
        assert node.gelled is True
        assert Occupancy.objects.active().filter(node=node).count() == 0
        leftover = TeamItem.objects.get(team=team, item_type=ItemType.GEL)
        assert leftover.quantity == 1

    def test_evicts_everyone_and_lets_nobody_claim(self, running_game, hard, team):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        other = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo", balance=400)
        previous = occupy(node, other, slot=1, floor=1, source=AcquisitionSource.ATTEMPT)
        give(team, ItemType.GEL)

        use_gel(team, node)

        node.refresh_from_db()
        previous.refresh_from_db()
        assert node.gelled is True
        assert previous.released_at is not None
        assert previous.release_reason == ReleaseReason.GELLED
        assert Occupancy.objects.active().filter(node=node).count() == 0
        with pytest.raises(Conflict, match="گِل"):
            claim_node(other, node)
        with pytest.raises(Conflict, match="گِل"):
            claim_node(team, node)

    def test_rejects_center(self, running_game, team):
        center = Node.objects.create(
            board=Board.GIRLS,
            code="CENTER",
            name="مرکز",
            level=LevelConfig.objects.get(level=Level.CENTER),
        )
        give(team, ItemType.GEL)

        with pytest.raises(Conflict):
            use_gel(team, center)
        assert TeamItem.objects.filter(team=team, item_type=ItemType.GEL).exists()
        center.refresh_from_db()
        assert center.gelled is False

    def test_second_gel_is_refused(self, running_game, hard, team):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        give(team, ItemType.GEL, quantity=2)

        use_gel(team, node)
        with pytest.raises(Conflict):
            use_gel(team, node)
        leftover = TeamItem.objects.get(team=team, item_type=ItemType.GEL)
        assert leftover.quantity == 1

    def test_notifies_the_teams_that_were_inside(self, running_game, hard, team, django_user_model):
        from notifications.models import Message, Notification

        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        other = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo")
        occupant = django_user_model.objects.create_user("bravo-user", password="x", team=other)
        occupy(node, other, slot=1, floor=1)
        give(team, ItemType.GEL)

        use_gel(team, node)

        message = Message.objects.get(sender_label="گِل")
        assert "گِل گرفته شد" in message.body
        # The house is «Hard 1» and the team that gelled it is named, so the
        # occupant learns who did it, not just that it happened.
        assert "Hard 1" in message.body
        assert team.name in message.body
        assert Notification.objects.filter(user=occupant, message=message).exists()

    def test_gels_spawn_and_toll(self, running_game, team):
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
        give(team, ItemType.GEL, quantity=2)

        use_gel(team, spawn)
        use_gel(team, toll)

        spawn.refresh_from_db()
        toll.refresh_from_db()
        assert spawn.gelled is True
        assert toll.gelled is True
        with pytest.raises(Conflict, match="گِل"):
            claim_spawn(team, spawn)

    def test_locks_only_the_team_s_board(self, running_game, hard, team):
        girls = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        boys = Node.objects.create(board=Board.BOYS, code="h1", name="Hard 1", level=hard)
        give(team, ItemType.GEL)

        use_gel(team, girls)

        girls.refresh_from_db()
        boys.refresh_from_db()
        assert girls.gelled is True
        assert boys.gelled is False

    def test_open_duel_is_refused(self, running_game, hard, team, django_user_model):
        from django.contrib.auth.models import Permission

        from duels.models import Duel, Room

        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        other = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo")
        target = occupy(node, other, slot=1, floor=1)
        judge = django_user_model.objects.create_user("judge-gel", password="x")
        judge.user_permissions.add(Permission.objects.get(codename="judge_duel"))
        room = Room.objects.create(name="R", link="https://skyroom.test/r", mentor=judge)
        Duel.objects.create(
            attacker=team,
            attacked=other,
            node=node,
            target=target,
            floor=1,
            stake=1,
            room=room,
            mentor=judge,
        )
        give(team, ItemType.GEL)

        with pytest.raises(Conflict, match="دوئل"):
            use_gel(team, node)
        node.refresh_from_db()
        target.refresh_from_db()
        assert node.gelled is False
        assert target.released_at is None
        assert TeamItem.objects.filter(team=team, item_type=ItemType.GEL).exists()

    def test_fake_document_cannot_sit_on_a_gelled_node(self, running_game, hard, team):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        give(team, ItemType.GEL)
        use_gel(team, node)
        give(team, ItemType.FAKE_DOCUMENT)

        with pytest.raises(Conflict, match="گِل"):
            use_fake_document(team, node)

    def test_restart_unlocks_gelled_nodes(self, running_game, hard, team):
        from game.services.reset import restart_game

        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        give(team, ItemType.GEL)
        use_gel(team, node)

        summary = restart_game()

        node.refresh_from_db()
        assert summary["gelled_nodes"] == 1
        assert node.gelled is False


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
    assert BOARD_GELLED in published
    assert BOARD_NODE_CLAIMED not in published
