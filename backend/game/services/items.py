"""Consume inventory items and apply their board effects.

Fake-document grants write `Occupancy(source=item)`. Gel does not seat anyone:
it evicts the house and locks the node until the next restart.
"""

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from game.models import (
    AcquisitionSource,
    FloorReward,
    GameSettings,
    Level,
    Node,
    Occupancy,
    ReleaseReason,
)
from teams.models import ItemType, Team, TeamItem

from .events import BOARD_GELLED, BOARD_NODE_CLAIMED, BOARD_RELEASED, publish_on_commit
from .mentor import Conflict
from .movement import reject_if_gelled

_UNPLAYABLE_LEVELS = frozenset({Level.SPAWN, Level.TOLL})


def consume_item(team: Team, item_type: str) -> TeamItem | None:
    """Spend one unit. Deletes the row when the stack is emptied."""
    item = TeamItem.objects.select_for_update().filter(team=team, item_type=item_type).first()
    if item is None or item.quantity < 1:
        raise Conflict("این آیتم در کوله‌پشتی نیست.")
    if item.quantity == 1:
        item.delete()
        return None
    TeamItem.objects.filter(pk=item.pk).update(quantity=F("quantity") - 1)
    item.refresh_from_db(fields=["quantity"])
    return item


def _require_running() -> None:
    if not GameSettings.load().is_running:
        raise Conflict("بازی در حال اجرا نیست.")


def _reject_gelled(node: Node) -> None:
    reject_if_gelled(node)


def _node_has_open_duel(occupancies: list[Occupancy]) -> bool:
    if not occupancies:
        return False
    from duels.models import Duel

    return Duel.objects.open().filter(target_id__in=[row.pk for row in occupancies]).exists()


def _notify_gelled(node: Node, team_ids: list[int]) -> None:
    if not team_ids:
        return
    from game.notices import house_gelled

    house_gelled(node.code, node.name or node.code, list(team_ids))


def _reject_unplayable(node: Node) -> None:
    if node.level_id in _UNPLAYABLE_LEVELS:
        raise Conflict("این خانه با آیتم قابل تملک نیست.")


def _playable_floors(node: Node) -> list[int]:
    floors = list(
        FloorReward.objects.filter(level_id=node.level_id)
        .order_by("floor")
        .values_list("floor", flat=True)
    )
    if not floors:
        raise Conflict("این خانه طبقهٔ قابل تملک ندارد.")
    return floors


def _lock_occupancies(node: Node) -> list[Occupancy]:
    return list(
        Occupancy.objects.active()
        .select_related("team", "node__level")
        .select_for_update(of=("self",))
        .filter(node_id=node.pk)
        .order_by("pk")
    )


def _still_active(occupancies: list[Occupancy]) -> list[Occupancy]:
    return [occupancy for occupancy in occupancies if occupancy.released_at is None]


def _held_floors(occupancies: list[Occupancy]) -> set[int]:
    return {occupancy.floor for occupancy in occupancies if occupancy.floor is not None}


def _soft_release(occupancy: Occupancy, reason: str = ReleaseReason.ITEM_TAKEOVER) -> None:
    occupancy.released_at = timezone.now()
    occupancy.release_reason = reason
    occupancy.save(update_fields=["released_at", "release_reason"])


def _choose_victim(occupancies: list[Occupancy], team: Team) -> Occupancy:
    others = [occupancy for occupancy in occupancies if occupancy.team_id != team.pk]
    if not others:
        raise Conflict("ظرفیت این خانه پر شده است.")
    others.sort(
        key=lambda occupancy: (occupancy.floor is not None, occupancy.floor or 0, occupancy.pk)
    )
    return others[0]


def _clear_attempt_fields(occupancy: Occupancy, floor: int) -> Occupancy:
    occupancy.source = AcquisitionSource.ITEM
    occupancy.floor = floor
    occupancy.grade = None
    occupancy.grade_multiplier = None
    occupancy.question = None
    occupancy.question_assigned_at = None
    occupancy.expires_at = None
    occupancy.is_spawn = False
    occupancy.save(
        update_fields=[
            "source",
            "floor",
            "grade",
            "grade_multiplier",
            "question",
            "question_assigned_at",
            "expires_at",
            "is_spawn",
        ]
    )
    return occupancy


def _create_item_holding(team: Team, node: Node, *, floor: int, slot: int) -> Occupancy:
    try:
        holding = Occupancy.objects.create(
            team=team,
            node=node,
            slot=slot,
            floor=floor,
            source=AcquisitionSource.ITEM,
        )
    except IntegrityError as exc:
        raise Conflict("این خانه هم‌زمان توسط تیم دیگری گرفته شد.") from exc
    holding.node = node
    holding.team = team
    return holding


def _lowest_free_slot(occupancies: list[Occupancy], capacity: int) -> int | None:
    taken = {occupancy.slot for occupancy in occupancies}
    return next((slot for slot in range(1, capacity + 1) if slot not in taken), None)


def _publish_takeover(team: Team, node: Node, *, released: bool) -> None:
    if released:
        publish_on_commit(
            BOARD_RELEASED,
            {"node": node.code, "reason": ReleaseReason.ITEM_TAKEOVER},
            board=team.board,
        )
    publish_on_commit(BOARD_NODE_CLAIMED, {"team": team.code, "node": node.code}, board=team.board)


@transaction.atomic
def use_fake_document(team: Team, node: Node) -> Occupancy:
    """Grant this team exactly one floor on the node, evicting if the house is full."""
    _require_running()
    node = Node.objects.select_for_update().select_related("level").get(pk=node.pk)
    _reject_unplayable(node)
    _reject_gelled(node)
    consume_item(team, ItemType.FAKE_DOCUMENT)

    locked = _lock_occupancies(node)
    floors = _playable_floors(node)
    ours = next((occupancy for occupancy in locked if occupancy.team_id == team.pk), None)
    released = False

    if ours is not None and ours.floor is not None:
        holding = _clear_attempt_fields(ours, ours.floor)
        _publish_takeover(team, node, released=False)
        return holding

    available = [floor for floor in floors if floor not in _held_floors(locked)]
    if ours is not None:
        if not available:
            raise Conflict("طبقهٔ آزادی روی این خانه نیست.")
        holding = _clear_attempt_fields(ours, available[0])
        _publish_takeover(team, node, released=False)
        return holding

    slot = _lowest_free_slot(locked, node.level.capacity)
    floor = available[0] if available else None
    if slot is None:
        victim = _choose_victim(locked, team)
        floor = victim.floor if victim.floor is not None else floor
        _soft_release(victim)
        released = True
        slot = victim.slot
        remaining = [occupancy for occupancy in _still_active(locked) if occupancy.pk != victim.pk]
        if floor is None:
            leftover = [f for f in floors if f not in _held_floors(remaining)]
            if not leftover:
                raise Conflict("طبقهٔ آزادی روی این خانه نیست.")
            floor = leftover[0]
    if floor is None:
        raise Conflict("طبقهٔ آزادی روی این خانه نیست.")

    holding = _create_item_holding(team, node, floor=floor, slot=slot)
    _publish_takeover(team, node, released=released)
    return holding


@transaction.atomic
def use_gel(team: Team, node: Node) -> list[Occupancy]:
    """Evict everyone on the node and lock it. Nobody sits here afterwards."""
    _require_running()
    if node.level_id == Level.CENTER or node.code == "CENTER":
        raise Conflict("خانهٔ مرکز را نمی‌توان گل گرفت.")

    node = Node.objects.select_for_update().select_related("level").get(pk=node.pk)
    _reject_gelled(node)

    locked = _lock_occupancies(node)
    if _node_has_open_duel(locked):
        raise Conflict("این خانه در حال دوئل است.")

    consume_item(team, ItemType.GEL)

    victim_ids: list[int] = []
    seen: set[int] = set()
    for occupancy in locked:
        _soft_release(occupancy, ReleaseReason.GELLED)
        if occupancy.team_id not in seen:
            seen.add(occupancy.team_id)
            victim_ids.append(occupancy.team_id)

    node.gelled = True
    node.save(update_fields=["gelled"])

    if locked:
        publish_on_commit(
            BOARD_RELEASED,
            {"node": node.code, "reason": ReleaseReason.GELLED},
            board=team.board,
        )
    publish_on_commit(BOARD_GELLED, {"node": node.code}, board=team.board)
    _notify_gelled(node, victim_ids)
    return locked


@transaction.atomic
def use_gilari(team: Team) -> None:
    """Spend 100 Gilari. No board, wallet, or inbox side effects."""
    consume_item(team, ItemType.GILARI_100)
