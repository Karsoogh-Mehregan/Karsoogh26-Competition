"""Reopen attempts whose clock ran out while nobody was playing.

`Occupancy.expires_at` is wall-clock, so pausing the game does not pause a
team's question timer. Reopening un-releases the seat and hands the team a
fresh clock; a seat another team has taken since is refused, not stolen back.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from game.models import Occupancy, ReleaseReason


def attempt_conflict(occupancy: Occupancy) -> str | None:
    """Why this released row cannot be seated again, or None."""
    active = Occupancy.objects.active().exclude(pk=occupancy.pk)
    if active.filter(node_id=occupancy.node_id, slot=occupancy.slot).exists():
        return "slot taken since"
    if (
        occupancy.floor is not None
        and active.filter(node_id=occupancy.node_id, floor=occupancy.floor).exists()
    ):
        return "floor taken since"
    if active.filter(
        team_id=occupancy.team_id, node_id=occupancy.node_id, source=occupancy.source
    ).exists():
        return "team already holds this node"
    return None


def reopen_attempts(
    occupancies, *, minutes: int | None = None
) -> tuple[list[Occupancy], list[tuple[Occupancy, str]]]:
    """Give each attempt a fresh clock, un-releasing the ones already swept.

    `minutes` defaults to the node level's `attempt_ttl_minutes`. Rows that are
    graded, submitted, questionless or released for any reason other than
    expiry are left alone. Returns (reopened, [(skipped, reason)]).
    """
    now = timezone.now()
    reopened: list[Occupancy] = []
    skipped: list[tuple[Occupancy, str]] = []

    with transaction.atomic():
        for occupancy in occupancies:
            reason = _refuses(occupancy)
            if reason:
                skipped.append((occupancy, reason))
                continue

            fields = ["expires_at"]
            if occupancy.released_at is not None:
                conflict = attempt_conflict(occupancy)
                if conflict:
                    skipped.append((occupancy, conflict))
                    continue
                occupancy.released_at = None
                occupancy.release_reason = ""
                fields += ["released_at", "release_reason"]

            ttl = minutes or occupancy.node.level.attempt_ttl_minutes
            occupancy.expires_at = now + timedelta(minutes=ttl)
            occupancy.save(update_fields=fields)
            reopened.append(occupancy)

    return reopened, skipped


def _refuses(occupancy: Occupancy) -> str | None:
    if occupancy.question_id is None:
        return "no question assigned"
    if occupancy.grade is not None:
        return "already graded"
    if occupancy.released_at is not None and occupancy.release_reason != ReleaseReason.EXPIRED:
        return f"released as {occupancy.release_reason}"
    if Occupancy.objects.filter(pk=occupancy.pk, submission__isnull=False).exists():
        return "already answered"
    return None
