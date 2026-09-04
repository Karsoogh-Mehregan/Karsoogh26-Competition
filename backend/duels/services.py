"""Opening and settling duels.

Two moves, and everything else here supports one of them.

`request_duel` is the expensive one: it decides whether a challenge is legal,
charges for it, and books a judge. All of that has to happen together — a team
charged for a duel that found no judge would be robbed — so it is one
transaction, and the reads that decide it are taken under row locks.

`resolve_duel` is the judge naming a winner. It moves the floor and the money,
once, and never again: a closed duel stays closed.

The rules this enforces, from the design doc:

* The building must be **full** — every slot taken and every one of them owned.
  A reservation nobody has graded yet is not an owner, so a house with an open
  attempt on it cannot be duelled for.
* The attacker must be **adjacent** to it, by the same reachability the board
  uses for movement, one-way roads included.
* One live duel per team, counting both roles, and a rest window after each.
* The stake is paid up front, refunded on a win and handed to the defender on a
  loss.
* The winner takes the floor outright, with no question to answer for it.
"""

import logging

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
from game.services.events import (
    BOARD_NODE_CLAIMED,
    BOARD_RELEASED,
    DUEL_UPDATED,
    publish_on_commit,
)
from game.services.movement import expandable_node_ids, is_reachable
from teams.ledger import InsufficientFunds, apply_balance_change
from teams.models import BalanceReason, Team

from .exceptions import (
    AlreadyInDuel,
    BuildingNotFull,
    DuelClosed,
    GameNotRunning,
    InvalidTarget,
    NoRoomAvailable,
    NotAdjacent,
    OnCooldown,
    StakeUnaffordable,
)
from .models import Duel, DuelStatus, Room

logger = logging.getLogger("karsoogh")

# Levels that have no floors to own, so nothing on them can be duelled for.
_UNDUELLABLE_LEVELS = frozenset({Level.SPAWN, Level.TOLL})


# ---- pricing ---------------------------------------------------------------


def duel_cost(occupancy: Occupancy) -> int:
    """What challenging this seat costs, from the floor's own price row."""
    return FloorReward.objects.get(
        level_id=occupancy.node.level_id, floor=occupancy.floor
    ).duel_cost


# ---- eligibility -----------------------------------------------------------


def cooldown_until(team: Team):
    """When this team may duel again, or None if it may right now.

    The window is per team, not per house: a team with three houses must not be
    challengeable once per house inside the same rest period.
    """
    if team.last_duel_at is None:
        return None
    minutes = GameSettings.load().duel_cooldown_minutes
    if not minutes:
        return None
    ready_at = team.last_duel_at + timezone.timedelta(minutes=minutes)
    return ready_at if ready_at > timezone.now() else None


def open_duel_for(team: Team) -> Duel | None:
    """The team's live duel, in either role. At most one exists."""
    return Duel.objects.open().detailed().for_team(team).first()


def _assert_free(team: Team, *, as_defender: bool = False) -> None:
    """Neither side may already be duelling, and neither may still be resting."""
    if open_duel_for(team) is not None:
        raise AlreadyInDuel(
            "تیم مقابل هم‌اکنون در یک دوئل است." if as_defender else "شما هم‌اکنون یک دوئل باز دارید."
        )
    ready_at = cooldown_until(team)
    if ready_at is not None:
        raise OnCooldown(
            "تیم مقابل هنوز در فاصلهٔ استراحت پس از دوئل قبلی است."
            if as_defender
            else "هنوز در فاصلهٔ استراحت پس از دوئل قبلی هستید."
        )


def building_is_full(node: Node, occupancies: list[Occupancy] | None = None) -> bool:
    """Every slot taken, and every one of them owned by a graded team.

    Two conditions, not one. A node at capacity whose third seat is an ungraded
    reservation has no third owner yet, and the rules sheet asks for a house
    whose floors all have owners.
    """
    if node.level_id in _UNDUELLABLE_LEVELS:
        return False
    if occupancies is None:
        occupancies = list(Occupancy.objects.active().filter(node_id=node.pk))
    if len(occupancies) < node.level.capacity:
        return False
    return all(occupancy.floor is not None for occupancy in occupancies)


def challengeable_targets(team: Team) -> list[dict]:
    """The table of «who you may duel», one row per contestable floor.

    Every owned floor of every full building next door, minus this team's own
    seats and minus anyone who is already duelling or resting. Rows carry their
    price so the UI never has to price a floor itself.
    """
    reachable_from = expandable_node_ids(team)
    if not reachable_from:
        return []

    candidates = (
        Occupancy.objects.active()
        .filter(team__board=team.board)
        .exclude(team=team)
        .filter(floor__isnull=False)
        .exclude(node__level_id__in=_UNDUELLABLE_LEVELS)
        .select_related("node__level", "team")
        .order_by("node__code", "floor")
    )

    by_node: dict[int, list[Occupancy]] = {}
    for occupancy in Occupancy.objects.active().select_related("node__level"):
        by_node.setdefault(occupancy.node_id, []).append(occupancy)

    # Nodes this team already sits on are out: winning would seat it twice on
    # one building, which `occ_one_unit_per_team` exists to prevent.
    own_nodes = set(Occupancy.objects.active().filter(team=team).values_list("node_id", flat=True))
    busy_team_ids = _busy_team_ids()

    prices = _price_table()
    rows = []
    for occupancy in candidates:
        node = occupancy.node
        if node.pk in own_nodes or occupancy.team_id in busy_team_ids:
            continue
        if not building_is_full(node, by_node.get(node.pk, [])):
            continue
        if not is_reachable(node, reachable_from):
            continue
        rows.append(
            {
                "occupancy_id": occupancy.pk,
                "node_code": node.code,
                "node_name": node.name,
                "level": node.level_id,
                "floor": occupancy.floor,
                "team": occupancy.team,
                "cost": prices.get((node.level_id, occupancy.floor), 0),
            }
        )
    return rows


def _busy_team_ids() -> set[int]:
    """Teams that cannot be drawn into a duel right now: duelling, or resting."""
    busy = set()
    for duel in Duel.objects.open().values_list("attacker_id", "attacked_id"):
        busy.update(duel)

    minutes = GameSettings.load().duel_cooldown_minutes
    if minutes:
        since = timezone.now() - timezone.timedelta(minutes=minutes)
        busy.update(Team.objects.filter(last_duel_at__gt=since).values_list("pk", flat=True))
    return busy


def _price_table() -> dict[tuple[str, int], int]:
    """Every floor's duel price in one query, keyed by (level, floor)."""
    return {
        (reward.level_id, reward.floor): reward.duel_cost for reward in FloorReward.objects.all()
    }


# ---- the judge queue -------------------------------------------------------


def _available_rooms():
    """Active rooms whose judge still holds the permission and is free.

    `users_with_perm` is borrowed from the notifications app on purpose: it
    answers "who was *given* this job", by explicit grant, rather than
    `has_perm`, which is True for every superuser. A room pointing at someone
    who has since lost `judge_duel` would take duels the judge could not then
    close, so it drops out of rotation on its own.
    """
    from notifications.services import users_with_perm

    from .permissions import JUDGE_PERM

    busy_mentor_ids = Duel.objects.open().values_list("mentor_id", flat=True)
    return (
        Room.objects.filter(is_active=True, mentor__is_active=True)
        .filter(mentor__in=users_with_perm(JUDGE_PERM))
        .exclude(mentor_id__in=busy_mentor_ids)
        .select_related("mentor")
    )


def next_room() -> Room:
    """Take the next room off the circular queue and send it to the back.

    Least-recently-assigned first, never-assigned ahead of all of them, so the
    rotation is fair over the whole event rather than only over the teams that
    happen to be duelling now. Locked for update: two simultaneous challenges
    must not both be handed the same judge.
    """
    room = (
        _available_rooms()
        .select_for_update(of=("self",))
        .order_by(F("last_assigned_at").asc(nulls_first=True), "pk")
        .first()
    )
    if room is None:
        raise NoRoomAvailable("در حال حاضر داور آزادی برای دوئل نیست. کمی بعد دوباره تلاش کنید.")
    Room.objects.filter(pk=room.pk).update(last_assigned_at=timezone.now())
    return room


def rooms_available() -> bool:
    return _available_rooms().exists()


# ---- opening a duel --------------------------------------------------------


@transaction.atomic
def request_duel(attacker: Team, target_id: int) -> Duel:
    """Challenge the team sitting on `target_id` for that floor.

    Everything is checked before a rial moves, and the whole thing is one
    transaction: a refused duel leaves no charge, and a charge that cannot find
    a judge is rolled back with it.
    """
    if not GameSettings.load().is_running:
        raise GameNotRunning("بازی در حال اجرا نیست.")

    target = (
        Occupancy.objects.active()
        .select_related("node__level", "team")
        .select_for_update(of=("self",))
        .filter(pk=target_id)
        .first()
    )
    if target is None:
        raise InvalidTarget("این واحد دیگر در اختیار آن تیم نیست.")
    if target.team_id == attacker.pk:
        raise InvalidTarget("نمی‌توانید به خانهٔ خودتان دوئل بزنید.")
    if target.floor is None:
        raise InvalidTarget("این واحد هنوز صاحبی ندارد.")

    node = target.node
    if node.level_id in _UNDUELLABLE_LEVELS:
        raise InvalidTarget("این خانه قابل دوئل نیست.")

    occupancies = list(
        Occupancy.objects.active()
        .select_for_update(of=("self",))
        .filter(node_id=node.pk)
        .order_by("pk")
    )
    if not building_is_full(node, occupancies):
        raise BuildingNotFull("فقط به ساختمانی که همهٔ طبقاتش صاحب دارد می‌توان دوئل زد.")
    if any(occupancy.team_id == attacker.pk for occupancy in occupancies):
        raise InvalidTarget("شما خودتان در این ساختمان واحد دارید.")

    if not is_reachable(node, expandable_node_ids(attacker)):
        raise NotAdjacent("فقط به ساختمان‌های مجاور خودتان می‌توانید دوئل بزنید.")

    defender = target.team
    _assert_free(attacker)
    _assert_free(defender, as_defender=True)

    stake = duel_cost(target)
    room = next_room()

    try:
        apply_balance_change(
            attacker,
            -stake,
            reason=BalanceReason.DUEL,
            detail=f"{node.code} f{target.floor} vs {defender.code}",
        )
    except InsufficientFunds as exc:
        raise StakeUnaffordable("موجودی تیم برای ورودی این دوئل کافی نیست.") from exc

    try:
        duel = Duel.objects.create(
            attacker=attacker,
            attacked=defender,
            node=node,
            target=target,
            floor=target.floor,
            stake=stake,
            room=room,
            mentor=room.mentor,
        )
    except IntegrityError as exc:
        # One of the partial uniques: another challenge for the same seat, or
        # for one of these teams, committed while this one was being assembled.
        raise AlreadyInDuel("هم‌زمان دوئل دیگری روی این واحد آغاز شد.") from exc

    duel.attacker = attacker
    duel.attacked = defender
    duel.node = node
    duel.room = room

    _announce(duel)
    _notify(duel, opened=True)
    return duel


# ---- settling it -----------------------------------------------------------


@transaction.atomic
def resolve_duel(duel: Duel, winner: Team, *, by) -> Duel:
    """Close a duel on the judge's word. Moves the floor and the money.

    The judge names a winner and nothing else — no draw, no forfeit verdict, no
    server-side clock. A team that never turned up is simply not the winner, and
    the five-minute rule is applied by the judge in the room.

    Attacker wins: the defender's seat is released as `duel_lost`, the attacker
    takes the same slot and floor without answering anything, and the stake
    comes back. Defender wins: nothing moves on the board and the stake becomes
    the defender's.
    """
    locked = (
        Duel.objects.select_for_update()
        .select_related("attacker", "attacked", "node__level", "room", "mentor")
        .get(pk=duel.pk)
    )
    if locked.status != DuelStatus.OPEN:
        raise DuelClosed("این دوئل قبلاً بسته شده است.")
    if winner.pk not in (locked.attacker_id, locked.attacked_id):
        raise InvalidTarget("برنده باید یکی از دو طرف دوئل باشد.")

    loser = locked.attacked if winner.pk == locked.attacker_id else locked.attacker

    # `node.code` rather than `node_id`: the ledger is read by organisers, and
    # the debit written when the duel opened names the node the same way.
    where = f"{locked.node.code} f{locked.floor}"
    if winner.pk == locked.attacker_id:
        _transfer_floor(locked)
        apply_balance_change(
            locked.attacker,
            locked.stake,
            reason=BalanceReason.DUEL,
            detail=f"بازگشت ورودی دوئل {where}",
        )
    else:
        apply_balance_change(
            locked.attacked,
            locked.stake,
            reason=BalanceReason.DUEL,
            detail=f"برد دوئل {where}",
        )

    now = timezone.now()
    locked.status = DuelStatus.CLOSED
    locked.winner = winner
    locked.loser = loser
    locked.resolved_by = by
    locked.resolved_at = now
    locked.save(update_fields=["status", "winner", "loser", "resolved_by", "resolved_at"])

    # The rest window starts for both sides at once — the rules count taking
    # part, not winning.
    Team.objects.filter(pk__in=(locked.attacker_id, locked.attacked_id)).update(last_duel_at=now)

    _announce(locked)
    _notify(locked, opened=False)
    return locked


def _transfer_floor(duel: Duel) -> None:
    """Hand the contested seat to the attacker, in place.

    The defender's row is soft-released like every other retirement, and a fresh
    row takes the same slot and floor. `source=duel` marks it as owned without
    an attempt, which is what stops the board offering a question for it and
    what makes grading elsewhere on the node route around the floor instead of
    re-ranking it away.
    """
    target = (
        Occupancy.objects.active().select_for_update(of=("self",)).filter(pk=duel.target_id).first()
    )
    if target is None:
        # The defender lost the seat some other way while the duel was running
        # — an item takeover, most likely. The duel still resolves and the money
        # still moves; there is simply no floor left to hand over.
        logger.warning("Duel %s won but target occupancy %s is gone", duel.pk, duel.target_id)
        return

    floor = target.floor if target.floor is not None else duel.floor
    slot = target.slot
    target.released_at = timezone.now()
    target.release_reason = ReleaseReason.DUEL_LOST
    target.save(update_fields=["released_at", "release_reason"])

    Occupancy.objects.create(
        team=duel.attacker,
        node_id=duel.node_id,
        slot=slot,
        floor=floor,
        source=AcquisitionSource.DUEL,
    )


# ---- fan-out ---------------------------------------------------------------


def participant_user_ids(duel: Duel) -> list[int]:
    """Everyone who may see this duel: both teams' logins, plus the judge."""
    from accounts.models import User

    ids = set(
        User.objects.filter(team_id__in=(duel.attacker_id, duel.attacked_id)).values_list(
            "pk", flat=True
        )
    )
    ids.add(duel.mentor_id)
    return sorted(ids)


def _announce(duel: Duel) -> None:
    """Two frames: one addressed to the duel's people, one for the whole board.

    The addressed one refreshes the duel page for the three accounts involved.
    The board one only goes out when a floor actually moved, and it is public
    because a changed owner is public.
    """
    publish_on_commit(
        DUEL_UPDATED,
        {"id": duel.pk, "status": duel.status},
        recipients=participant_user_ids(duel),
    )
    if duel.status != DuelStatus.CLOSED or duel.winner_id != duel.attacker_id:
        return
    publish_on_commit(
        BOARD_RELEASED,
        {
            "team": duel.attacked.code,
            "node": duel.node.code,
            "reason": ReleaseReason.DUEL_LOST,
        },
        board=duel.attacker.board,
    )
    publish_on_commit(
        BOARD_NODE_CLAIMED,
        {"team": duel.attacker.code, "node": duel.node.code},
        board=duel.attacker.board,
    )


def _notify(duel: Duel, *, opened: bool) -> None:
    """Write the duel into the inboxes. Never allowed to break the duel itself."""
    from . import notices

    if opened:
        notices.duel_opened(duel)
    else:
        notices.duel_closed(duel)
