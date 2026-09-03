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


DIFFICULTY_LAYOUTS = {
    MinesweeperDifficulty.EASY: {"width": 9, "height": 9, "mine_count": 10},
    MinesweeperDifficulty.MEDIUM: {"width": 16, "height": 16, "mine_count": 40},
    MinesweeperDifficulty.HARD: {"width": 30, "height": 16, "mine_count": 99},
}

DIFFICULTY_BASE_SCORES = {
    MinesweeperDifficulty.EASY: 100,
    MinesweeperDifficulty.MEDIUM: 250,
    MinesweeperDifficulty.HARD: 500,
}


def empty_layout_board():
    """Unpopulated mine layout. Services fill `cells` when generating a game.

    Populated shape (``height`` rows of ``width`` cells)::

        {"cells": [[{"mine": bool, "adjacent_mines": int}, ...], ...]}
    """
    return {"cells": []}


# Historical alias: migration 0001 references this name as the JSONField default.
empty_board = empty_layout_board


def empty_progress_board():
    """Unpopulated per-attempt progress. Services fill `cells` when starting play.

    Populated shape (``height`` rows of ``width`` cells)::

        {"cells": [[{"revealed": bool, "flagged": bool}, ...], ...]}
    """
    return {"cells": []}


def _layout_matches_difficulty() -> Q:
    condition = Q()
    for difficulty, layout in DIFFICULTY_LAYOUTS.items():
        condition |= Q(difficulty=difficulty, **layout)
    return condition


class MinesweeperSettings(models.Model):
    """Per-node configuration. Does not store a board, team, or score."""

    node = models.OneToOneField(
        "game.Node",
        on_delete=models.CASCADE,
        related_name="minesweeper_settings",
    )
    enabled = models.BooleanField(default=True)
    difficulty = models.CharField(max_length=8, choices=MinesweeperDifficulty.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Minesweeper settings"

    def __str__(self):
        state = "on" if self.enabled else "off"
        return f"{self.node} {self.get_difficulty_display()} ({state})"


class MinesweeperGame(models.Model):
    """One generated board. Created when a team starts play on a configured node."""

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
        default=empty_layout_board,
        help_text=(
            "Mine layout only: {cells: [[{mine, adjacent_mines}, ...], ...]}. "
            "Do not expose this JSON to teams while an attempt is in progress."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(
                condition=_layout_matches_difficulty(),
                name="minesweepergame_layout_matches_difficulty",
            ),
        ]

    def __str__(self):
        return f"{self.node} game {self.pk} {self.get_difficulty_display()}"


class MinesweeperAttemptQuerySet(models.QuerySet):
    def in_progress(self):
        return self.filter(status=MinesweeperStatus.IN_PROGRESS)


class MinesweeperAttempt(models.Model):
    """One team's execution of a generated MinesweeperGame."""

    game = models.ForeignKey(
        MinesweeperGame,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.PROTECT,
        related_name="minesweeper_attempts",
    )
    status = models.CharField(
        max_length=12,
        choices=MinesweeperStatus.choices,
        default=MinesweeperStatus.IN_PROGRESS,
    )
    board = models.JSONField(
        default=empty_progress_board,
        help_text=(
            "Per-attempt progress: {cells: [[{revealed, flagged}, ...], ...]}. "
            "Mine locations stay on the game layout."
        ),
    )
    score = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MinesweeperAttemptQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            CheckConstraint(
                condition=(
                    Q(status=MinesweeperStatus.IN_PROGRESS, finished_at__isnull=True)
                    | Q(
                        status__in=[MinesweeperStatus.WON, MinesweeperStatus.LOST],
                        finished_at__isnull=False,
                    )
                ),
                name="minesweeperattempt_finished_at_matches_status",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "status"], name="msweeper_att_team_status_idx"),
            models.Index(fields=["game", "team"], name="msweeper_att_game_team_idx"),
        ]

    def __str__(self):
        return f"{self.team} game {self.game_id} ({self.get_status_display()})"
