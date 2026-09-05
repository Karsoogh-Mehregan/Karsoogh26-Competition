"""End-of-game settlement: pay every team the networth of the floors it holds.

`FloorReward.networth` is the only price no live path ever reads — points,
duel_cost and buyout_cost are all charged during play, networth is the value a
holding is worth once the clock has stopped. Nothing pays it automatically,
because "the game is over" is an organiser's decision, not a state the server
reaches on its own.
"""

from dataclasses import dataclass

from django.db import transaction

from game.models import FloorReward, Occupancy
from teams.ledger import apply_balance_change
from teams.models import BalanceEvent, BalanceReason, Team


@dataclass(frozen=True)
class TeamSettlement:
    team: Team
    amount: int
    floors: int
    already_settled: bool


def _rewards() -> dict[tuple[int, int], int]:
    return {
        (reward.level_id, reward.floor): reward.networth for reward in FloorReward.objects.all()
    }


def plan_settlement(board: str | None = None) -> list[TeamSettlement]:
    rewards = _rewards()
    settled = set(
        BalanceEvent.objects.filter(reason=BalanceReason.NETWORTH).values_list("team_id", flat=True)
    )

    teams = Team.objects.all().order_by("code")
    holdings = Occupancy.objects.active().select_related("node").filter(floor__isnull=False)
    if board:
        teams = teams.filter(board=board)
        holdings = holdings.filter(team__board=board)

    totals: dict[int, list[int]] = {}
    for holding in holdings:
        amount, count = totals.setdefault(holding.team_id, [0, 0])
        totals[holding.team_id] = [
            amount + rewards.get((holding.node.level_id, holding.floor), 0),
            count + 1,
        ]

    plan = []
    for team in teams:
        amount, floors = totals.get(team.pk, [0, 0])
        plan.append(
            TeamSettlement(
                team=team,
                amount=amount,
                floors=floors,
                already_settled=team.pk in settled,
            )
        )
    return plan


@transaction.atomic
def settle_networth(board: str | None = None) -> list[TeamSettlement]:
    """Credit each team its held floors' networth, once and only once."""
    paid = []
    for entry in plan_settlement(board):
        if entry.already_settled or entry.amount == 0:
            continue
        apply_balance_change(
            entry.team,
            entry.amount,
            reason=BalanceReason.NETWORTH,
            detail=f"{entry.floors} floors",
        )
        paid.append(entry)
    return paid
