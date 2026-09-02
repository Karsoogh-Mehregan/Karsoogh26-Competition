"""The pre-game entry sheet: a few short questions that gate the spawn claim.

Answers are integers, so the sheet grades itself the moment a team submits —
no mentor, no `Submission`, no `Occupancy`. Clearing it (or waiting out the
grace window) is what unlocks `teams/<code>/claim-start/`.
"""

from django.db import IntegrityError, transaction
from django.db.models import Count, Max
from django.utils import timezone

from game.exceptions import (
    EntryAlreadyAnswered,
    GameNotRunning,
    NoEntryQuestions,
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
        EntryAttempt.objects.filter(team=team).select_related("question").order_by("position")
    )


@transaction.atomic
def assign_entry_sheet(team: Team) -> list[EntryAttempt]:
    """Draw the team's sheet once; every later call returns the same rows.

    Questions are drawn least-served first with a random tiebreak, so a pool
    larger than the sheet spreads evenly instead of favouring whatever a pure
    random draw lands on. Seed exactly `entry_question_count` active questions
    and every team gets that same sheet.
    """
    # Serialise concurrent first-reads for this team; the unique constraints
    # are the real backstop on SQLite, where the row lock is a no-op.
    Team.objects.select_for_update().filter(pk=team.pk).first()

    existing = _sheet(team)
    missing = GameSettings.load().entry_question_count - len(existing)
    if missing <= 0:
        return existing

    served_ids = [attempt.question_id for attempt in existing]
    drawn = list(
        EntryQuestion.objects.filter(is_active=True)
        .exclude(pk__in=served_ids)
        .annotate(serve_count=Count("attempts"))
        .order_by("serve_count", "?")[:missing]
    )
    if len(drawn) < missing:
        raise NoEntryQuestions(
            f"Need {missing} more active entry question(s) to fill the sheet; "
            f"{len(drawn)} available."
        )

    next_position = len(existing) + 1
    try:
        EntryAttempt.objects.bulk_create(
            EntryAttempt(team=team, question=question, position=next_position + offset)
            for offset, question in enumerate(drawn)
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

    attempt = (
        EntryAttempt.objects.select_for_update()
        .select_related("question")
        .filter(team=team, question__code=code)
        .first()
    )
    if attempt is None:
        raise NotOnEntrySheet(f"Question '{code}' is not on this team's entry sheet.")
    if attempt.answered_at is not None:
        raise EntryAlreadyAnswered(f"Question '{code}' has already been answered.")

    attempt.answer = answer
    attempt.is_correct = answer == attempt.question.answer
    attempt.answered_at = timezone.now()
    attempt.save(update_fields=["answer", "is_correct", "answered_at"])

    if attempt.is_correct:
        _record_draft_order(team, settings)

    return attempt


def correct_count(team: Team) -> int:
    return EntryAttempt.objects.filter(team=team, is_correct=True).count()


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
