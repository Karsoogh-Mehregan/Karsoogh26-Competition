from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from game.models import (
    AcquisitionSource,
    FloorReward,
    GameSettings,
    Occupancy,
    ReleaseReason,
    _round_half_up,
)
from teams.ledger import apply_balance_change
from teams.models import BalanceReason

from .events import BOARD_GRADED, BOARD_RELEASED, publish_on_commit

# TODO: duel / buyout flow should be implemented later.
MENTOR_RELEASE_REASONS = (ReleaseReason.ZERO_GRADE, ReleaseReason.EXPIRED)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "این عملیات در وضعیت فعلی مجاز نیست."
    default_code = "conflict"


DEFAULT_MAX_GRADE = 100


def floor_points(rewards: dict[int, int], floor: int | None, multiplier: Decimal | None) -> int:
    if floor is None or multiplier is None:
        return 0
    return _round_half_up(rewards[floor] * multiplier)


def grade_ratio(grade: int, max_grade: int) -> Decimal:
    return (Decimal(grade) / Decimal(max_grade)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def max_grade_for(holding: Occupancy) -> int:
    """A holding graded without a question row is scored on the plain 0-100 scale."""
    if holding.question_id is None:
        return DEFAULT_MAX_GRADE
    return holding.question.max_grade


def _floors_for_ranked(
    level, ranked: list, reserved_floors: set[int], reward_floors: set[int]
) -> list[int]:
    """Best-first floor numbers that do not collide with item-held floors.

    With no item seats this is the existing  N, N-1, …, 1  packing. Otherwise
    graded teams take the lowest free reward floors, still best-on-top.
    """
    if not reserved_floors:
        return [len(ranked) - index for index in range(len(ranked))]

    candidates = sorted((reward_floors or set(range(1, level.capacity + 1))) - reserved_floors)
    if len(ranked) > len(candidates):
        raise Conflict("ظرفیت این خانه پر شده است.")
    return list(reversed(candidates[: len(ranked)]))


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
        .select_related("question")
        .select_for_update(of=("self",))
        .order_by("pk")
    }
    if holding.pk not in locked:
        raise Conflict("این واحد آزاد شده است.")

    holding = locked[holding.pk]
    holding.node = node
    holding.awarded = 0

    if holding.question_assigned_at is None:
        raise Conflict("هنوز سؤالی به این تیم تخصیص داده نشده است.")
    if holding.grade is not None:
        raise Conflict("این تلاش از قبل نمره دارد.")

    max_grade = max_grade_for(holding)
    if grade > max_grade:
        raise ValueError(f"Grade must be between 0 and {max_grade}.")

    holding.grade = grade
    holding.grade_multiplier = grade_ratio(grade, max_grade)
    holding.save(update_fields=["grade", "grade_multiplier"])
    # Registered before the floor re-rank so the early return below still announces.
    publish_on_commit(BOARD_GRADED, {"node": node.code})

    rewards = {
        reward.floor: reward.points for reward in FloorReward.objects.filter(level_id=level.pk)
    }

    if not _keeps_floor(holding, grade, max_grade):
        return _pay_and_release_without_ranking(holding, locked, rewards, grade, max_grade)

    ranked = [
        occupancy
        for occupancy in locked.values()
        if occupancy.grade and occupancy.source != AcquisitionSource.ITEM
    ]
    if not ranked:
        return _release_unless_perfect(holding, grade, max_grade)

    if len(ranked) > level.capacity:
        raise Conflict("ظرفیت این خانه پر شده است.")

    # Ranked on the ratio, not the raw grade: two teams on one node can hold
    # questions with different max_grade, which makes raw grades incomparable.
    ranked.sort(key=lambda occupancy: (-occupancy.grade_multiplier, occupancy.question_assigned_at))
    reserved_floors = {
        occupancy.floor
        for occupancy in locked.values()
        if occupancy.source == AcquisitionSource.ITEM and occupancy.floor is not None
    }
    before = {
        occupancy.pk: floor_points(rewards, occupancy.floor, occupancy.grade_multiplier)
        for occupancy in ranked
    }

    Occupancy.objects.filter(pk__in=[occupancy.pk for occupancy in ranked]).update(floor=None)
    assigned = _floors_for_ranked(level, ranked, reserved_floors, set(rewards))
    for occupancy, floor in zip(ranked, assigned, strict=True):
        occupancy.floor = floor
    Occupancy.objects.bulk_update(ranked, ["floor"])

    for occupancy in ranked:
        delta = (
            floor_points(rewards, occupancy.floor, occupancy.grade_multiplier)
            - before[occupancy.pk]
        )
        if delta > 0:
            apply_balance_change(
                occupancy.team,
                delta,
                reason=BalanceReason.GRADE,
                detail=node.code,
            )
        if occupancy.pk == holding.pk:
            holding.awarded = max(delta, 0)

    holding.team.refresh_from_db(fields=["balance"])
    return _release_unless_perfect(holding, grade, max_grade)


def _keeps_floor(holding: Occupancy, grade: int, max_grade: int) -> bool:
    return holding.question_id is None or grade >= max_grade


def _pay_and_release_without_ranking(
    holding: Occupancy,
    locked: dict[int, Occupancy],
    rewards: dict[int, int],
    grade: int,
    max_grade: int,
) -> Occupancy:
    """Pay a partial grade off the floor it would have taken, moving nobody.

    The holding is about to be released, so ranking it would push the teams above
    it up a floor and then leave a hole behind when it goes.
    """
    taken = {
        occupancy.floor
        for occupancy in locked.values()
        if occupancy.floor is not None and occupancy.pk != holding.pk
    }
    free = sorted(floor for floor in rewards if floor not in taken)
    holding.awarded = floor_points(rewards, free[0] if free else None, holding.grade_multiplier)
    if holding.awarded > 0:
        apply_balance_change(
            holding.team,
            holding.awarded,
            reason=BalanceReason.GRADE,
            detail=holding.node.code,
        )
        holding.team.refresh_from_db(fields=["balance"])
    return _release_unless_perfect(holding, grade, max_grade)


def _release_unless_perfect(holding: Occupancy, grade: int, max_grade: int) -> Occupancy:
    """Anything short of full marks keeps the money but gives the slot back."""
    if _keeps_floor(holding, grade, max_grade):
        return holding

    awarded = holding.awarded
    if holding.floor is not None:
        holding.floor = None
        holding.save(update_fields=["floor"])
    holding = release_attempt(
        holding,
        ReleaseReason.ZERO_GRADE if grade == 0 else ReleaseReason.PARTIAL_GRADE,
    )
    holding.awarded = awarded
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
