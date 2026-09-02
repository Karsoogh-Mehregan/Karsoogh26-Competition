"""Wipe a run so the board can be played again.

Only ever reached through `IsGameGod` plus an explicit confirmation, because it
throws away every move of a contest. It resets *state*, never *content*: nodes,
edges, questions and the economy tables survive, so the next run starts on the
same map with the same question bank.
"""

import logging

from django.db import transaction

from game.models import GameSettings, GameStatus, Occupancy
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

    teams = Team.objects.update(
        balance=settings_row.initial_balance,
        color=None,
        draft_order=None,
        last_duel_at=None,
    )

    settings_row.status = GameStatus.NOT_STARTED
    # Cleared so the elapsed clock restarts from the next kick-off. `ends_at` is
    # left alone: an organiser typed it in, and silently dropping it is worse
    # than a stale value they can see and change.
    settings_row.started_at = None
    settings_row.save(update_fields=["status", "started_at"])

    summary = {
        "occupancies": deleted.get("game.Occupancy", 0),
        "submissions": deleted.get("game.Submission", 0),
        "teams": teams,
    }
    logger.warning("Game restarted by %s: %s", getattr(by, "username", "unknown"), summary)
    return summary
