"""Wipe a run so the board can be played again.

Only ever reached through `IsGameGod` plus an explicit confirmation, because it
throws away every move of a contest. It resets *state*, never *content*: nodes,
edges, questions and the economy tables survive, so the next run starts on the
same map with the same question bank.
"""

import logging

from django.db import transaction

from game.models import EntryAttempt, GameSettings, GameStatus, Occupancy
from notifications.models import Message, MessageKind
from teams.models import Team

logger = logging.getLogger("karsoogh")


@transaction.atomic
def restart_game(*, by=None) -> dict:
    """Clear the board, refund every team, and put the game back to not-started.

    Returns what it removed, so the caller can report it honestly instead of a
    bare "done".
    """
    settings_row = GameSettings.load()

    # Submissions and TeamQuestions hang off Occupancy with CASCADE, so one
    # delete takes all three. Questions themselves are content and stay.
    # delete() returns (total_across_all_models, per_model_counts) — report the
    # per-model numbers, or "occupancies" silently includes the cascade.
    _total, deleted = Occupancy.objects.all().delete()

    # The sheet hangs off Team, not Occupancy, so the cascade above misses it.
    # Left behind, last run's correct answers would clear the gate again and no
    # team would ever see a sheet. The EntryQuestion bank is content and stays.
    entry_attempts, _ = EntryAttempt.objects.all().delete()

    # Automatic messages narrate the run that just ended — "your answer scored
    # 90" about an occupancy that no longer exists is noise on the next run.
    # Hand-written announcements are content and survive, same rule as the
    # question bank. Notification rows cascade off the messages.
    system_messages, _ = Message.objects.filter(kind=MessageKind.SYSTEM).delete()

    teams = Team.objects.update(
        balance=settings_row.initial_balance,
        color=None,
        draft_order=None,
        last_duel_at=None,
    )

    # Zero the run ledger so both timers start over. `duration_minutes` is left
    # alone: an organiser set it deliberately, and it is the length of the game,
    # not a fact about the run that just ended.
    settings_row.status = GameStatus.NOT_STARTED
    settings_row.started_at = None
    settings_row.accumulated_seconds = 0
    settings_row.running_since = None
    settings_row.save(
        update_fields=["status", "started_at", "accumulated_seconds", "running_since"]
    )

    summary = {
        "occupancies": deleted.get("game.Occupancy", 0),
        "submissions": deleted.get("game.Submission", 0),
        "entry_attempts": entry_attempts,
        "system_messages": system_messages,
        "teams": teams,
    }
    logger.warning("Game restarted by %s: %s", getattr(by, "username", "unknown"), summary)
    return summary
