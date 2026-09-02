"""The pre-game entry sheet: a few short questions that gate the spawn claim.

Answers are integers, so the sheet grades itself the moment a team submits —
no mentor, no `Submission`, no `Occupancy`. Clearing it (or waiting out the
grace window) is what unlocks `teams/<code>/claim-start/`.

Each question is one shot, but a team that got one wrong may swap it for a
fresh question up to `GameSettings.entry_max_refreshes` times. Swapping retires
the old row rather than editing it, so a discarded question can never be drawn
for that team again.
"""

from django.db import IntegrityError, transaction
from django.db.models import Count, Max
from django.utils import timezone

from game.exceptions import (
    EntryAlreadyAnswered,
    EntryAnswerWasCorrect,
    EntryNotAnswered,
    GameNotRunning,
    NoEntryQuestions,
    NoEntryRefreshesLeft,
    NotOnEntrySheet,
)
from game.models import EntryAttempt, EntryQuestion, GameSettings
from teams.models import Team

from .mentor import Conflict

# draft_order is unique, so two teams qualifying at once will collide. The
# loser of the race just takes the next number.
_DRAFT_ORDER_ATTEMPTS = 5


def _sheet(team: Team) -> list[EntryAttempt]:
    return list(
        EntryAttempt.objects.current()
        .filter(team=team)
        .select_related("question")
        .order_by("position")
    )


def _draw(team: Team, count: int) -> list[EntryQuestion]:
    """Least-served questions the team has never been shown, retired ones included.

    The random tiebreak spreads a pool larger than the sheet evenly instead of
    favouring whatever a pure random draw lands on.
    """
    seen_ids = EntryAttempt.objects.filter(team=team).values_list("question_id", flat=True)
    drawn = list(
        EntryQuestion.objects.filter(is_active=True)
        .exclude(pk__in=seen_ids)
        .annotate(serve_count=Count("attempts"))
        .order_by("serve_count", "?")[:count]
    )
    if len(drawn) < count:
        raise NoEntryQuestions(
            f"Need {count} more active entry question(s); {len(drawn)} available."
        )
    return drawn


@transaction.atomic
def assign_entry_sheet(team: Team) -> list[EntryAttempt]:
    """Draw the team's sheet once; every later call returns the same rows.

    Seed exactly `entry_question_count` active questions and every team gets
    that same sheet; seed more and the draw spreads across the pool.
    """
    # Serialise concurrent first-reads for this team; the unique constraints
    # are the real backstop on SQLite, where the row lock is a no-op.
    Team.objects.select_for_update().filter(pk=team.pk).first()

    existing = _sheet(team)
    missing = GameSettings.load().entry_question_count - len(existing)
    if missing <= 0:
        return existing

    next_position = len(existing) + 1
    try:
        EntryAttempt.objects.bulk_create(
            EntryAttempt(team=team, question=question, position=next_position + offset)
            for offset, question in enumerate(_draw(team, missing))
        )
    except IntegrityError:
        # Another request filled the sheet first — its rows are the sheet.
        return _sheet(team)

    return _sheet(team)


@transaction.atomic
def answer_entry_question(team: Team, code: str, answer: int) -> EntryAttempt:
    """Record and instantly mark one entry answer. One shot per question."""
    settings = GameSettings.load()
    if not settings.is_running:
        raise GameNotRunning("Game is not running.")

    attempt = _lock_attempt(team, code)
    if attempt.answered_at is not None:
        raise EntryAlreadyAnswered(f"Question '{code}' has already been answered.")

    attempt.answer = answer
    attempt.is_correct = answer == attempt.question.answer
    attempt.answered_at = timezone.now()
    attempt.save(update_fields=["answer", "is_correct", "answered_at"])

    if attempt.is_correct:
        _record_draft_order(team, settings)

    return attempt


@transaction.atomic
def refresh_entry_question(team: Team, code: str) -> EntryAttempt:
    """Swap a wrongly-answered question for a fresh one at the same position.

    Retires the old row instead of clearing it, so the team's history stays
    readable and `entryattempt_no_repeat` keeps the discarded question from
    being drawn for them again.
    """
    settings = GameSettings.load()
    if not settings.is_running:
        raise GameNotRunning("Game is not running.")

    if refreshes_used(team) >= settings.entry_max_refreshes:
        raise NoEntryRefreshesLeft(
            f"Team has used all {settings.entry_max_refreshes} entry-question swap(s)."
        )

    attempt = _lock_attempt(team, code)
    if attempt.answered_at is None:
        raise EntryNotAnswered(f"Question '{code}' has not been answered yet.")
    if attempt.is_correct:
        raise EntryAnswerWasCorrect(f"Question '{code}' was answered correctly.")

    replacement = _draw(team, 1)[0]

    attempt.replaced_at = timezone.now()
    attempt.save(update_fields=["replaced_at"])

    return EntryAttempt.objects.create(
        team=team,
        question=replacement,
        position=attempt.position,
    )


def _lock_attempt(team: Team, code: str) -> EntryAttempt:
    attempt = (
        EntryAttempt.objects.current()
        .select_for_update()
        .select_related("question")
        .filter(team=team, question__code=code)
        .first()
    )
    if attempt is None:
        raise NotOnEntrySheet(f"Question '{code}' is not on this team's entry sheet.")
    return attempt


def correct_count(team: Team) -> int:
    return EntryAttempt.objects.current().filter(team=team, is_correct=True).count()


def refreshes_used(team: Team) -> int:
    return EntryAttempt.objects.filter(team=team, replaced_at__isnull=False).count()


def _record_draft_order(team: Team, settings: GameSettings) -> None:
    """Stamp finishing order the moment a team clears the sheet."""
    if team.draft_order is not None:
        return
    if correct_count(team) < settings.entry_required_correct:
        return

    for _ in range(_DRAFT_ORDER_ATTEMPTS):
        highest = Team.objects.aggregate(highest=Max("draft_order"))["highest"] or 0
        try:
            with transaction.atomic():
                updated = Team.objects.filter(pk=team.pk, draft_order__isnull=True).update(
                    draft_order=highest + 1
                )
        except IntegrityError:
            continue
        if updated:
            team.draft_order = highest + 1
        return


def entry_status(team: Team) -> dict:
    """Everything the SPA needs to render the sheet and decide if the map is open."""
    settings = GameSettings.load()
    attempts = _sheet(team)
    correct = sum(1 for attempt in attempts if attempt.is_correct)
    qualified = correct >= settings.entry_required_correct
    grace_over = settings.entry_grace_over
    used = refreshes_used(team)

    return {
        "required_correct": settings.entry_required_correct,
        "correct_count": correct,
        "answered_count": sum(1 for attempt in attempts if attempt.answered_at is not None),
        "total_count": len(attempts),
        "qualified": qualified,
        "grace_over": grace_over,
        "grace_ends_at": settings.entry_grace_ends_at,
        "can_claim_start": qualified or grace_over,
        "draft_order": team.draft_order,
        "refreshes_used": used,
        "refreshes_left": max(0, settings.entry_max_refreshes - used),
        "attempts": attempts,
    }


def can_claim_start(team: Team) -> bool:
    settings = GameSettings.load()
    return settings.entry_grace_over or correct_count(team) >= settings.entry_required_correct


def require_entry_clearance(team: Team) -> None:
    """Gate `claim-start/` on the sheet. Raises the 409 the view lets bubble up."""
    if can_claim_start(team):
        return
    settings = GameSettings.load()
    raise Conflict(
        f"برای گرفتن خانهٔ شروع باید حداقل {settings.entry_required_correct} "
        f"سؤال ورودی را درست پاسخ دهید."
    )
