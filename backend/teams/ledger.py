"""Atomic balance changes with an audit trail."""

from django.db.models import F

from .models import BalanceEvent, Team


class InsufficientFunds(Exception):
    """Raised when a debit would take a team's balance below zero."""


def apply_balance_change(
    team: Team,
    delta: int,
    *,
    reason: str,
    detail: str = "",
) -> Team:
    """Apply *delta* to team.balance, record a BalanceEvent, and return the team.

    Raises InsufficientFunds for debits that exceed the current balance.
    Does nothing (and returns the team unchanged) when delta == 0.
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
