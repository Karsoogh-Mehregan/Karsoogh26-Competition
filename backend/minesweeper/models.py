from django.db import models
from django.db.models import CheckConstraint, F, Q

# Sanity ceiling for an admin-entered board. A 40x40 grid is already far beyond
# anything playable inside a contest slot; the cap exists so a typo cannot ask
# the generator for a million cells.
MAX_DIMENSION = 40


class MinesweeperDifficulty(models.TextChoices):
    """The three difficulties seeded by migration 0007.

    Not the closed set any more: `DifficultyConfig` rows are data, and organisers
    may add, retune or remove them in admin. These constants only name the rows
    that ship, for seeds and tests.
    """

    EASY = "easy", "آسان"
    MEDIUM = "medium", "متوسط"
    HARD = "hard", "سخت"


class MinesweeperStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "در حال اجرا"
    WON = "won", "برنده"
    LOST = "lost", "باخته"


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


class DifficultyConfig(models.Model):
    """An editable difficulty, the way `game.LevelConfig` is an editable level.

    Board size and mine count are rows, not constants, so organisers can retune
    a difficulty from admin between rounds. A generated `MinesweeperGame` copies
    the numbers it was built with, so retuning never reshapes a board a team is
    already playing.
    """

    key = models.SlugField(max_length=16, primary_key=True)
    label = models.CharField(max_length=32, help_text="Shown to players, in Persian.")
    width = models.PositiveSmallIntegerField()
    height = models.PositiveSmallIntegerField()
    mine_count = models.PositiveSmallIntegerField()
    sort_order = models.PositiveSmallIntegerField(
        default=0, help_text="Order in admin and in any difficulty picker; low first."
    )

    class Meta:
        ordering = ["sort_order", "key"]
        verbose_name = "difficulty config"
        verbose_name_plural = "difficulty configs"
        constraints = [
            CheckConstraint(
                condition=Q(
                    width__gte=2,
                    width__lte=MAX_DIMENSION,
                    height__gte=2,
                    height__lte=MAX_DIMENSION,
                ),
                name="difficultyconfig_dimension_range",
            ),
            CheckConstraint(
                # At least one mine, and at least one safe cell to open.
                condition=Q(mine_count__gte=1, mine_count__lt=F("width") * F("height")),
                name="difficultyconfig_mine_count_range",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.width}×{self.height}, {self.mine_count})"

    @property
    def cell_count(self) -> int:
        return self.width * self.height


class MinesweeperSettings(models.Model):
    """Per-node configuration. Does not store a board, team, or result."""

    node = models.OneToOneField(
        "game.Node",
        on_delete=models.CASCADE,
        related_name="minesweeper_settings",
    )
    enabled = models.BooleanField(default=True)
    difficulty = models.ForeignKey(
        DifficultyConfig,
        on_delete=models.PROTECT,
        related_name="node_settings",
        db_column="difficulty",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Minesweeper settings"

    def __str__(self):
        state = "on" if self.enabled else "off"
        return f"{self.node} {self.difficulty_id} ({state})"


class MinesweeperGame(models.Model):
    """One generated board. Created when a team starts play on a configured node."""

    node = models.ForeignKey(
        "game.Node",
        on_delete=models.PROTECT,
        related_name="minesweeper_games",
    )
    difficulty = models.ForeignKey(
        DifficultyConfig,
        on_delete=models.PROTECT,
        related_name="games",
        db_column="difficulty",
    )
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

    def __str__(self):
        return f"{self.node} game {self.pk} {self.difficulty_id}"


class MinesweeperAttemptQuerySet(models.QuerySet):
    def in_progress(self):
        return self.filter(status=MinesweeperStatus.IN_PROGRESS)

    def won(self):
        return self.filter(status=MinesweeperStatus.WON)


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
