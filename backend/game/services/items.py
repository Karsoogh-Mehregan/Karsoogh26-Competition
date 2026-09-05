"""Consume inventory items and apply their board effects.

A fake document names the floor it wants: the player picks a house, then a
storey in it, and takes that one — turning out whoever owned it — as an
`Occupancy(source=item)`. Gel seats nobody: it evicts the whole house and locks
the node until the next restart.
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

# Tiers with no floors to take (`FloorReward` has no rows for a spawn or a
# gate) plus the city hall, which is nobody's to forge a deed to.
_UNPLAYABLE_LEVELS = frozenset({Level.SPAWN, Level.TOLL, Level.CENTER})


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


def _notify_gelled(node: Node, by_team: Team, team_ids: list[int]) -> None:
    if not team_ids:
        return
    from game.notices import house_gelled

    house_gelled(node.code, node.name or node.code, by_team.name, list(team_ids))


def _notify_floor_taken(node: Node, floor: int, by_team: Team, team_id: int) -> None:
    from game.notices import floor_taken

    floor_taken(node.code, node.name or node.code, floor, by_team.name, team_id)


def _reject_unplayable(node: Node) -> None:
    if node.level_id == Level.CENTER or node.code == "CENTER":
        raise Conflict("خانهٔ مرکز را نمی‌توان با سند جعلی گرفت.")
    if node.level_id in _UNPLAYABLE_LEVELS:
        raise Conflict("این خانه با آیتم قابل تملک نیست.")


def _reject_ungellable(node: Node) -> None:
    """The city hall and the toll gates are not houses, so they cannot be gelled.

    A gate is the only road onto the ring beyond it; gelling one would wall off
    a whole ring for every team at once. It is recognised three ways because a
    Designer may move a node between tiers: the `toll` level, the `C34`/`C45`
    connector codes, and a minesweeper board — the board is the gate.
    """
    if node.level_id == Level.CENTER or node.code == "CENTER":
        raise Conflict("خانهٔ مرکز را نمی‌توان گِل گرفت.")
    if (
        node.level_id == Level.TOLL
        or node.code.upper().startswith(("C34", "C45"))
        or _has_minesweeper_board(node)
    ):
        raise Conflict("عوارضی را نمی‌توان گِل گرفت.")


def _has_minesweeper_board(node: Node) -> bool:
    """Read through the reverse accessor: `minesweeper` depends on `game`."""
    settings = getattr(node, "minesweeper_settings", None)
    return bool(settings and settings.enabled)


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


def _soft_release(occupancy: Occupancy, reason: str = ReleaseReason.ITEM_TAKEOVER) -> None:
    occupancy.released_at = timezone.now()
    occupancy.release_reason = reason
    occupancy.save(update_fields=["released_at", "release_reason"])


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
def use_fake_document(team: Team, node: Node, floor: int) -> Occupancy:
    """Take the named floor of the house, turning out whoever owned it.

    The floor is the player's choice, not the server's: the backpack shows the
    storeys and who is in each, and this takes exactly the one that was clicked.
    Only that floor's owner is evicted — a neighbour who merely reserved a slot
    keeps it, which is why a house whose slots are all reserved can refuse a
    forged deed to a floor that reads as empty.

    The team's own seat is moved rather than duplicated, so one team never ends
    up holding two units of one building.
    """
    _require_running()
    node = Node.objects.select_for_update().select_related("level").get(pk=node.pk)
    _reject_unplayable(node)
    _reject_gelled(node)

    if floor not in _playable_floors(node):
        raise Conflict("این طبقه روی این خانه وجود ندارد.")

    locked = _lock_occupancies(node)
    victim = next((occupancy for occupancy in locked if occupancy.floor == floor), None)
    ours = next((occupancy for occupancy in locked if occupancy.team_id == team.pk), None)

    if victim is not None and victim.team_id == team.pk:
        raise Conflict("این طبقه از قبل در اختیار تیم شماست.")
    # The judge is about to decide this seat, and `Duel.target` protects the row.
    if victim is not None and _node_has_open_duel([victim]):
        raise Conflict("این طبقه موضوع یک دوئل باز است.")

    if ours is not None:
        slot = ours.slot
    else:
        # The victim's slot frees up the moment it is released, so it is left
        # out of the count rather than special-cased below.
        free_of = [row for row in locked if row is not victim]
        slot = _lowest_free_slot(free_of, node.level.capacity)
        if slot is None:
            raise Conflict("همهٔ واحدهای این ساختمان گرفته شده‌اند.")

    consume_item(team, ItemType.FAKE_DOCUMENT)

    if victim is not None:
        _soft_release(victim, ReleaseReason.ITEM_TAKEOVER)
        _notify_floor_taken(node, floor, team, victim.team_id)

    if ours is not None:
        holding = _clear_attempt_fields(ours, floor)
    else:
        holding = _create_item_holding(team, node, floor=floor, slot=slot)

    _publish_takeover(team, node, released=victim is not None)
    return holding


@transaction.atomic
def use_gel(team: Team, node: Node) -> list[Occupancy]:
    """Evict everyone on the node and lock it. Nobody sits here afterwards."""
    _require_running()
    # Deliberately not joining `minesweeper_settings` here: it is the nullable
    # side of an outer join, which Postgres refuses to lock.
    node = Node.objects.select_for_update().select_related("level").get(pk=node.pk)
    _reject_ungellable(node)
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
    _notify_gelled(node, team, victim_ids)
    return locked


@transaction.atomic
def use_gilari(team: Team) -> None:
    """Spend 100 Gilari. No board, wallet, or inbox side effects."""
    consume_item(team, ItemType.GILARI_100)
