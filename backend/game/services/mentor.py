from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from game.models import (
    FloorReward,
    GameSettings,
    GradeMultiplier,
    Occupancy,
    ReleaseReason,
    _round_half_up,
)
from teams.models import Team

from .events import BOARD_GRADED, BOARD_RELEASED, publish_on_commit

# TODO: duel / buyout flow should be implemented later.
MENTOR_RELEASE_REASONS = (ReleaseReason.ZERO_GRADE, ReleaseReason.EXPIRED)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "این عملیات در وضعیت فعلی مجاز نیست."
    default_code = "conflict"


def floor_points(rewards: dict[int, int], floor: int | None, multiplier: Decimal | None) -> int:
    if floor is None or multiplier is None:
        return 0
    return _round_half_up(rewards[floor] * multiplier)


@transaction.atomic
def grade_attempt(holding: Occupancy, grade: int) -> Occupancy:
    settings = GameSettings.load()
    if not settings.is_running:
        raise Conflict("بازی در حال اجرا نیست.")

    node = holding.node
    level = node.level

    locked = {
        occupancy.pk: occupancy
        for occupancy in Occupancy.objects.active()
        .filter(node_id=node.pk)
        .select_related("team")
        .select_for_update(of=("self",))
        .order_by("pk")
    }
    if holding.pk not in locked:
        raise Conflict("این واحد آزاد شده است.")

    holding = locked[holding.pk]
    holding.node = node

    if holding.question_assigned_at is None:
        raise Conflict("هنوز سؤالی به این تیم تخصیص داده نشده است.")
    if holding.grade is not None:
        raise Conflict("این تلاش از قبل نمره دارد.")

    holding.grade = grade
    holding.grade_multiplier = GradeMultiplier.factor_for(grade)
    holding.save(update_fields=["grade", "grade_multiplier"])
    # Registered before the floor re-rank so the early return below still announces.
    publish_on_commit(BOARD_GRADED, {"node": node.code})

    # Imported here, not at module scope: `notifications.services` reaches back
    # into `game.services.events` for the SSE publisher, so a top-level import
    # would close the loop while this package is still being built.
    from notifications import alerts

    alerts.grade_posted(holding)

    ranked = [occupancy for occupancy in locked.values() if occupancy.grade]
    if not ranked:
        return holding

    if len(ranked) > level.capacity:
        raise Conflict("ظرفیت این خانه پر شده است.")

    ranked.sort(key=lambda occupancy: (-occupancy.grade, occupancy.question_assigned_at))
    rewards = {
        reward.floor: reward.points for reward in FloorReward.objects.filter(level_id=level.pk)
    }
    before = {
        occupancy.pk: floor_points(rewards, occupancy.floor, occupancy.grade_multiplier)
        for occupancy in ranked
    }

    Occupancy.objects.filter(pk__in=[occupancy.pk for occupancy in ranked]).update(floor=None)
    for index, occupancy in enumerate(ranked):
        occupancy.floor = len(ranked) - index
    Occupancy.objects.bulk_update(ranked, ["floor"])

    for occupancy in ranked:
        delta = (
            floor_points(rewards, occupancy.floor, occupancy.grade_multiplier)
            - before[occupancy.pk]
        )
        if delta > 0:
            Team.objects.filter(pk=occupancy.team_id).update(balance=F("balance") + delta)
            # The team just graded already hears about its own result; this is
            # for the neighbours the re-rank moved up without them doing a thing.
            if occupancy.pk != holding.pk:
                occupancy.node = node
                alerts.floor_promoted(occupancy)

    holding.team.refresh_from_db(fields=["balance"])
    return holding


@transaction.atomic
def release_attempt(holding: Occupancy, reason: str) -> Occupancy:
    """Retire a failed attempt and free its slot. Floors and balances are untouched."""
    locked = (
        Occupancy.objects.active()
        .select_related("node", "team")
        .select_for_update(of=("self",))
        .filter(pk=holding.pk)
        .first()
    )
    if locked is None:
        raise Conflict("این واحد قبلاً آزاد شده است.")
    if locked.floor is not None:
        raise Conflict(
            "این تیم صاحب یک طبقه است و آزادسازی، طبقه را خالی می‌گذارد. "
            "انتقال مالکیت از مسیر دوئل یا خرید انجام می‌شود."
        )

    locked.released_at = timezone.now()
    locked.release_reason = reason
    locked.save(update_fields=["released_at", "release_reason"])
    publish_on_commit(
        BOARD_RELEASED,
        {"team": locked.team.code, "node": locked.node.code, "reason": reason},
    )

    holding.released_at = locked.released_at
    holding.release_reason = locked.release_reason
    return holding
