"""Buying a floor out from under the team that holds it.

The design doc's «مکانیک خرید»: a team that is stuck may pay a lot of money and
buy a unit. The team sitting in it is put out but loses nothing it was paid; the
buyer takes the floor and is paid the floor's points.

That is a duel without the meeting, and it is priced as one — every floor's
`FloorReward.buyout_cost` is a column an organiser tunes, next to `duel_cost`.
The rules that carry over from the duel are the ones about *reach*: the target
must be adjacent by the same reachability the board uses to move, one-way roads
included, and the buyer may not already sit in the house (winning would seat it
twice on one building). The rules that do **not** carry over are the ones about
the meeting: a house need not be full, there is no judge, no stake to refund and
no rest window. One rule is new: a seat under an open duel cannot be bought,
because `Duel.target` protects the row and the judge is about to decide it.

Two writes, one transaction: the price leaves the buyer, the holder's row is
soft-released as `bought_out`, a fresh row takes the same slot and floor with
`source=buyout`, and the floor's points land in the buyer's wallet. A refusal
anywhere in there leaves no charge behind.
"""

from django.db import IntegrityError, transaction
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
from teams.ledger import InsufficientFunds, apply_balance_change
from teams.models import BalanceReason, Team

from .events import BOARD_NODE_CLAIMED, BOARD_RELEASED, publish_on_commit
from .mentor import Conflict
from .movement import expandable_node_ids, is_reachable

# Levels that have no floors to own, so nothing on them can be bought.
_UNBUYABLE_LEVELS = frozenset({Level.SPAWN, Level.TOLL})


class BuyoutRefused(Conflict):
    """A refusal the player caused and can fix; the message is what they read."""


# ---- pricing ---------------------------------------------------------------


def _price_table() -> dict[tuple[str, int], tuple[int, int]]:
    """Every floor's (buyout price, points) in one query, keyed by (level, floor)."""
    return {
        (reward.level_id, reward.floor): (reward.buyout_cost, reward.points)
        for reward in FloorReward.objects.all()
    }


def buyout_cost(occupancy: Occupancy) -> int:
    """What buying this seat costs, from the floor's own price row."""
    return FloorReward.objects.get(
        level_id=occupancy.node.level_id, floor=occupancy.floor
    ).buyout_cost


# ---- eligibility -----------------------------------------------------------


def _duelled_occupancy_ids() -> set[int]:
    """Seats a judge is about to decide. Local import: duels depends on game."""
    from duels.models import Duel

    return set(Duel.objects.open().values_list("target_id", flat=True))


def buyable_targets(team: Team) -> list[dict]:
    """The table of «what you may buy», one row per purchasable floor.

    Every owned floor of every building next door, minus houses this team
    already sits in and minus seats under an open duel. Rows carry their price
    so the UI never has to price a floor itself.
    """
    reachable_from = expandable_node_ids(team)
    if not reachable_from:
        return []

    candidates = (
        Occupancy.objects.active()
        .filter(team__board=team.board)
        .exclude(team=team)
        .filter(floor__isnull=False)
        .exclude(node__level_id__in=_UNBUYABLE_LEVELS)
        .exclude(node__gelled=True)
        .select_related("node__level", "team")
        .order_by("node__code", "floor")
    )
    own_nodes = set(Occupancy.objects.active().filter(team=team).values_list("node_id", flat=True))
    duelled = _duelled_occupancy_ids()
    prices = _price_table()

    rows = []
    for occupancy in candidates:
        node = occupancy.node
        if node.pk in own_nodes or occupancy.pk in duelled:
            continue
        if not is_reachable(node, reachable_from):
            continue
        cost, points = prices.get((node.level_id, occupancy.floor), (0, 0))
        rows.append(
            {
                "occupancy_id": occupancy.pk,
                "node_code": node.code,
                "node_name": node.name,
                "level": node.level_id,
                "floor": occupancy.floor,
                "team": occupancy.team,
                "cost": cost,
                "points": points,
            }
        )
    return rows


# ---- the purchase ----------------------------------------------------------


@transaction.atomic
def buy_out(buyer: Team, target_id: int) -> Occupancy:
    """Take the seat `target_id` from its holder for the floor's buyout price.

    Everything is checked before a rial moves, and the whole thing is one
    transaction: a refused purchase leaves no charge, and a row conflict on the
    way in rolls the charge back with it.
    """
    if not GameSettings.load().is_running:
        raise BuyoutRefused("بازی در حال اجرا نیست.")

    target = (
        Occupancy.objects.active()
        .select_related("node__level", "team")
        .select_for_update(of=("self",))
        .filter(pk=target_id)
        .first()
    )
    if target is None:
        raise BuyoutRefused("این واحد دیگر در اختیار آن تیم نیست.")
    if target.team_id == buyer.pk:
        raise BuyoutRefused("این واحد از قبل مال شماست.")
    if target.floor is None:
        raise BuyoutRefused("این واحد هنوز صاحبی ندارد.")

    node: Node = target.node
    if node.gelled:
        raise BuyoutRefused("این خانه گل گرفته شده و ورود به آن ممکن نیست.")
    if node.level_id in _UNBUYABLE_LEVELS:
        raise BuyoutRefused("این خانه قابل خرید نیست.")
    if target.team.board != buyer.board:
        raise BuyoutRefused("این واحد در زمین شما نیست.")

    # Lock every seat on the node, in pk order, the same way `claim_node` and
    # the duels app do — so a purchase and a claim on one house serialise.
    occupancies = list(
        Occupancy.objects.active()
        .select_for_update(of=("self",))
        .filter(node_id=node.pk)
        .order_by("pk")
    )
    if any(occupancy.team_id == buyer.pk for occupancy in occupancies):
        raise BuyoutRefused("شما خودتان در این ساختمان واحد دارید.")
    if not is_reachable(node, expandable_node_ids(buyer)):
        raise BuyoutRefused("فقط واحدهای ساختمان‌های مجاور خودتان را می‌توانید بخرید.")
    if target.pk in _duelled_occupancy_ids():
        raise BuyoutRefused("این واحد در حال حاضر موضوع یک دوئل است.")

    reward = FloorReward.objects.get(level_id=node.level_id, floor=target.floor)
    holder = target.team
    where = f"{node.code} f{target.floor}"

    try:
        apply_balance_change(
            buyer,
            -reward.buyout_cost,
            reason=BalanceReason.BUYOUT,
            detail=f"خرید {where} از {holder.code}",
        )
    except InsufficientFunds as exc:
        raise BuyoutRefused("موجودی تیم برای خرید این واحد کافی نیست.") from exc

    # The holder goes without losing a rial: nothing paid for the floor is
    # clawed back, exactly as the doc says.
    target.released_at = timezone.now()
    target.release_reason = ReleaseReason.BOUGHT_OUT
    target.save(update_fields=["released_at", "release_reason"])

    try:
        holding = Occupancy.objects.create(
            team=buyer,
            node=node,
            slot=target.slot,
            floor=target.floor,
            source=AcquisitionSource.BUYOUT,
        )
    except IntegrityError as exc:
        raise BuyoutRefused("این واحد هم‌زمان توسط تیم دیگری گرفته شد.") from exc
    holding.node = node
    holding.team = buyer

    # «تیمی که خونه رو خریده امتیاز اون خونه رو میگیره»: the floor's full
    # points, as a perfect grade would have paid.
    apply_balance_change(
        buyer,
        reward.points,
        reason=BalanceReason.BUYOUT,
        detail=f"امتیاز طبقهٔ خریداری‌شده {where}",
    )

    publish_on_commit(
        BOARD_RELEASED,
        {"team": holder.code, "node": node.code, "reason": ReleaseReason.BOUGHT_OUT},
        board=buyer.board,
    )
    publish_on_commit(
        BOARD_NODE_CLAIMED,
        {"team": buyer.code, "node": node.code},
        board=buyer.board,
    )
    return holding
