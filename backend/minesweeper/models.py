from django.db import models
from django.db.models import CheckConstraint, Q


class MinesweeperDifficulty(models.TextChoices):
    EASY = "easy", "آسان"
    MEDIUM = "medium", "متوسط"
    HARD = "hard", "سخت"


class MinesweeperStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "در حال اجرا"
    WON = "won", "برنده"
    LOST = "lost", "باخته"


# The only legal board size and mine count for each difficulty.
DIFFICULTY_LAYOUTS = {
    MinesweeperDifficulty.EASY: {"width": 9, "height": 9, "mine_count": 10},
    MinesweeperDifficulty.MEDIUM: {"width": 16, "height": 16, "mine_count": 40},
    MinesweeperDifficulty.HARD: {"width": 30, "height": 16, "mine_count": 99},
}

# Base points awarded on a win, before the time bonus.
DIFFICULTY_BASE_SCORES = {
    MinesweeperDifficulty.EASY: 100,
    MinesweeperDifficulty.MEDIUM: 250,
    MinesweeperDifficulty.HARD: 500,
}


def empty_board():
    """Unpopulated server-side board. Services fill `cells` when generating a game.

    Populated shape (``height`` rows of ``width`` cells, top-to-bottom, left-to-right)::

        {"cells": [[{"mine": bool, "revealed": bool, "flagged": bool,
                     "adjacent_mines": int}, ...], ...]}

    ``mine`` on an unrevealed cell is server-only — never serialise it to a team.
    """
    return {"cells": []}


def _layout_matches_difficulty() -> Q:
    condition = Q()
    for difficulty, layout in DIFFICULTY_LAYOUTS.items():
        condition |= Q(difficulty=difficulty, **layout)
    return condition


class MinesweeperGameQuerySet(models.QuerySet):
    def in_progress(self):
        return self.filter(status=MinesweeperStatus.IN_PROGRESS)


class MinesweeperGame(models.Model):
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.PROTECT,
        related_name="minesweeper_games",
    )
    node = models.ForeignKey(
        "game.Node",
        on_delete=models.PROTECT,
        related_name="minesweeper_games",
    )
    difficulty = models.CharField(max_length=8, choices=MinesweeperDifficulty.choices)
    width = models.PositiveSmallIntegerField()
    height = models.PositiveSmallIntegerField()
    mine_count = models.PositiveSmallIntegerField()
    board = models.JSONField(
        default=empty_board,
        help_text=(
            "Server-side grid: {cells: [[{mine, revealed, flagged, adjacent_mines}, ...], ...]}. "
            "Do not expose unrevealed mines to teams."
        ),
    )
    status = models.CharField(
        max_length=12,
        choices=MinesweeperStatus.choices,
        default=MinesweeperStatus.IN_PROGRESS,
    )
    score = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MinesweeperGameQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            CheckConstraint(
                condition=_layout_matches_difficulty(),
                name="minesweepergame_layout_matches_difficulty",
            ),
            CheckConstraint(
                condition=(
                    Q(status=MinesweeperStatus.IN_PROGRESS, finished_at__isnull=True)
                    | Q(
                        status__in=[MinesweeperStatus.WON, MinesweeperStatus.LOST],
                        finished_at__isnull=False,
                    )
                ),
                name="minesweepergame_finished_at_matches_status",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "status"], name="msweeper_team_status_idx"),
        ]

    def __str__(self):
        return f"{self.team} {self.get_difficulty_display()} ({self.get_status_display()})"
