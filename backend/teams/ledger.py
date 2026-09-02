from django.db.models import F

from .models import BalanceEvent, Team


class InsufficientFunds(Exception):
    """The team cannot cover a negative delta."""


def apply_balance_change(
    team: Team,
    delta: int,
    *,
    reason: str,
    detail: str = "",
) -> Team:
    """Credit or debit `team.balance` and append a ledger row.

    `delta == 0` is a no-op so callers can pass a computed payout without
    filtering first. Negative deltas refuse to go below zero.
    """
    if delta == 0:
        return team

    qs = Team.objects.filter(pk=team.pk)
    if delta < 0:
        updated = qs.filter(balance__gte=-delta).update(balance=F("balance") + delta)
        if not updated:
            raise InsufficientFunds
    else:
        qs.update(balance=F("balance") + delta)

    team.refresh_from_db(fields=["balance"])
    BalanceEvent.objects.create(
        team=team,
        delta=delta,
        balance_after=team.balance,
        reason=reason,
        detail=detail[:128],
    )
    return team
