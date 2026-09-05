from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django.utils import timezone

from core.boards import Board

from .design import (
    ARCHETYPES,
    DEFAULT_HALO_STRENGTH,
    DEFAULT_TINT_STRENGTH,
    SECTOR_COUNT,
    NeighborhoodTheme,
    RoadStyle,
)
from .validators import validate_upload_extension, validate_upload_size

MAX_CAPACITY = 3


def _round_half_up(value: Decimal) -> int:
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class Level(models.TextChoices):
    SPAWN = "spawn", "شروع"
    EASY = "easy", "آسان"
    MEDIUM = "medium", "متوسط"
    HARD = "hard", "سخت"
    CENTER = "center", "مرکز شهر"
    TOLL = "toll", "عوارضی"


class ReleaseReason(models.TextChoices):
    ZERO_GRADE = "zero_grade", "نمره صفر"
    PARTIAL_GRADE = "partial_grade", "نمره ناقص"
    EXPIRED = "expired", "منقضی شد"
    DUEL_LOST = "duel_lost", "باخت دوئل"
    BOUGHT_OUT = "bought_out", "خریداری شد"
    ITEM_TAKEOVER = "item_takeover", "آیتم"


class AcquisitionSource(models.TextChoices):
    ATTEMPT = "attempt", "تلاش"
    ITEM = "item", "آیتم"
    DUEL = "duel", "دوئل"
    BUYOUT = "buyout", "خرید"


# Seats a team was *given* rather than earned by answering. They behave alike
# everywhere it matters: they expand reach without a grade, they are never
# offered a question, and grading elsewhere on the node must route around their
# floor rather than re-rank it. Behavioural checks go through this set so a
# fourth way of acquiring a floor is one line, not a search of the codebase.
GRANTED_SOURCES = frozenset(
    {AcquisitionSource.ITEM, AcquisitionSource.DUEL, AcquisitionSource.BUYOUT}
)


class GameStatus(models.TextChoices):
    NOT_STARTED = "not_started", "شروع نشده"
    RUNNING = "running", "در حال اجرا"
    PAUSED = "paused", "متوقف"
    FINISHED = "finished", "تمام شده"


class AnswerType(models.TextChoices):
    TEXT = "text", "متن"
    FILE = "file", "فایل"
    NUMERIC = "numeric", "عددی"


class LevelConfig(models.Model):
    level = models.CharField(max_length=8, primary_key=True, choices=Level.choices)

    capacity = models.PositiveSmallIntegerField()
    entry_cost = models.PositiveIntegerField()

    attempt_ttl_minutes = models.PositiveSmallIntegerField(
        default=15,
        help_text="Minutes the team has to answer after a question is assigned on this level.",
    )

    class Meta:
        verbose_name = "level config"
        verbose_name_plural = "level configs"
        constraints = [
            CheckConstraint(
                condition=Q(capacity__gte=1, capacity__lte=MAX_CAPACITY),
                name="levelconfig_capacity_range",
            ),
            CheckConstraint(
                condition=Q(attempt_ttl_minutes__gte=1),
                name="levelconfig_attempt_ttl_positive",
            ),
        ]

    def __str__(self):
        return self.get_level_display()


class FloorReward(models.Model):
    level = models.ForeignKey(
        LevelConfig, on_delete=models.CASCADE, related_name="floor_rewards", db_column="level"
    )
    floor = models.PositiveSmallIntegerField()
    points = models.IntegerField()
    networth = models.IntegerField(default=0, help_text="End-of-game value of holding this floor.")
    duel_cost = models.PositiveIntegerField(
        default=0, help_text="What challenging this floor costs the attacker."
    )
    buyout_cost = models.PositiveIntegerField(
        default=0, help_text="What buying this floor out from its holder costs."
    )

    class Meta:
        ordering = ["level", "floor"]
        constraints = [
            UniqueConstraint(fields=["level", "floor"], name="uniq_level_floor"),
            CheckConstraint(
                condition=Q(floor__gte=1, floor__lte=MAX_CAPACITY),
                name="floorreward_floor_range",
            ),
        ]

    def __str__(self):
        return f"{self.level_id} floor {self.floor} = {self.points}"


class GradeMultiplier(models.Model):
    grade = models.PositiveSmallIntegerField(unique=True)
    factor = models.DecimalField(max_digits=4, decimal_places=3)

    class Meta:
        ordering = ["grade"]
        constraints = [
            CheckConstraint(condition=Q(grade__lte=100), name="grademultiplier_grade_range"),
            CheckConstraint(
                condition=Q(factor__gte=0, factor__lte=1),
                name="grademultiplier_factor_range",
            ),
        ]

    def __str__(self):
        return f"{self.grade} -> {self.factor}"

    @classmethod
    def factor_for(cls, grade: int) -> Decimal:
        row = cls.objects.filter(grade__lte=grade).order_by("-grade").first()
        if row is None:
            raise ValueError(f"No GradeMultiplier breakpoint at or below {grade}; seed grade=0.")
        return row.factor


class Node(models.Model):
    # Each board holds its own full copy of the map, under the same codes: the
    # girls' `L1_0` and the boys' `L1_0` are two rows. Scoping the uniqueness
    # rather than prefixing the codes is what lets one graph_data.json render
    # both boards and one colour table serve both spawns.
    board = models.CharField(max_length=8, choices=Board.choices)
    code = models.SlugField(max_length=32)
    name = models.CharField(max_length=64, blank=True)
    level = models.ForeignKey(
        LevelConfig, on_delete=models.PROTECT, related_name="nodes", db_column="level"
    )
    # A Designer's pin. Blank means the renderer picks, and it picks so that no
    # two neighbours look alike; a pin is honoured even if it breaks that.
    archetype = models.CharField(max_length=32, blank=True, choices=ARCHETYPES)

    class Meta:
        ordering = ["board", "code"]
        constraints = [
            UniqueConstraint(fields=["board", "code"], name="node_unique_per_board"),
            # `choices` is only enforced by full_clean, and nothing here calls it.
            # Without this a blank board saves cleanly and the node belongs to
            # neither contest, which nothing else would notice.
            CheckConstraint(condition=Q(board__in=Board.values), name="node_board_valid"),
        ]

    def __str__(self):
        return self.name or self.code


class Edge(models.Model):
    """A link between two nodes. Directed ones run a -> b; undirected ones are
    normalised to a.id < b.id, so each unordered pair stores once.

    No board column: both endpoints carry one. A cross-board edge is rejected by
    `import_graph`, and would be untraversable anyway, because a node is only
    ever resolved as (the acting team's board, code).
    """

    a = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="edges_a")
    b = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="edges_b")
    directed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["a", "b"], name="edge_unique"),
            CheckConstraint(condition=Q(directed=True) | Q(a__lt=F("b")), name="edge_normalised"),
        ]

    def __str__(self):
        arrow = "->" if self.directed else "<->"
        return f"{self.a_id} {arrow} {self.b_id}"


class OccupancyQuerySet(models.QuerySet):
    def active(self):
        return self.filter(released_at__isnull=True)


class Occupancy(models.Model):
    node = models.ForeignKey(Node, on_delete=models.PROTECT, related_name="occupancies")
    team = models.ForeignKey("teams.Team", on_delete=models.PROTECT, related_name="occupancies")

    slot = models.PositiveSmallIntegerField()
    floor = models.PositiveSmallIntegerField(null=True, blank=True)

    grade = models.PositiveSmallIntegerField(null=True, blank=True)
    grade_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Snapshot of the curve at judging time, so points stay reproducible.",
    )
    question_assigned_at = models.DateTimeField(null=True, blank=True)
    question = models.ForeignKey(
        "Question",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="occupancies",
    )

    is_spawn = models.BooleanField(default=False)
    source = models.CharField(
        max_length=16,
        choices=AcquisitionSource.choices,
        default=AcquisitionSource.ATTEMPT,
    )
    expires_at = models.DateTimeField(null=True, blank=True)

    entered_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(max_length=16, blank=True, choices=ReleaseReason.choices)

    objects = OccupancyQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "occupancies"
        permissions = [("act_as_mentor", "Can perform mentor actions")]
        constraints = [
            UniqueConstraint(
                fields=["node", "slot"],
                condition=Q(released_at__isnull=True),
                name="occ_one_team_per_slot",
            ),
            UniqueConstraint(
                fields=["node", "floor"],
                condition=Q(released_at__isnull=True),
                name="occ_one_team_per_floor",
            ),
            UniqueConstraint(
                fields=["team", "node"],
                condition=Q(released_at__isnull=True, source=AcquisitionSource.ATTEMPT),
                name="occ_one_unit_per_team",
            ),
            CheckConstraint(
                condition=Q(slot__gte=1, slot__lte=MAX_CAPACITY),
                name="occ_slot_range",
            ),
            CheckConstraint(
                condition=Q(grade__isnull=True) | Q(grade__lte=100),
                name="occ_grade_range",
            ),
            CheckConstraint(
                condition=Q(grade__isnull=True) | Q(question_assigned_at__isnull=False),
                name="occ_graded_has_assigned_at",
            ),
            CheckConstraint(
                condition=Q(grade__isnull=True) | Q(grade_multiplier__isnull=False),
                name="occ_graded_has_multiplier",
            ),
        ]
        indexes = [
            models.Index(
                fields=["expires_at"],
                condition=Q(released_at__isnull=True),
                name="occ_active_expiry_idx",
            ),
        ]

    def __str__(self):
        return f"{self.team} @ {self.node} slot {self.slot}"

    @property
    def points(self) -> int:
        if self.floor is None or self.grade_multiplier is None:
            return 0
        reward = FloorReward.objects.get(level_id=self.node.level_id, floor=self.floor)
        return _round_half_up(reward.points * self.grade_multiplier)

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= timezone.now()


class GameSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    duel_cooldown_minutes = models.PositiveSmallIntegerField(
        default=5,
        help_text="Minutes a team must rest after a duel before it may take part in another.",
    )
    duel_deadline_minutes = models.PositiveSmallIntegerField(
        default=15,
        help_text=(
            "Unused. Duel timing is run by the judge in the meeting, not by the server: "
            "a team that does not show up is simply not named as the winner."
        ),
    )
    initial_balance = models.PositiveIntegerField(
        default=400,
        help_text="Every team starts here, entry sheet cleared or not.",
    )
    status = models.CharField(
        max_length=12, choices=GameStatus.choices, default=GameStatus.NOT_STARTED
    )
    leaderboard_public = models.BooleanField(default=False)
    leaderboard_frozen = models.BooleanField(
        default=False,
        help_text=(
            "When on, competing teams see a snapshot of the rankings taken at "
            "the freeze; organisers keep seeing live numbers."
        ),
    )
    leaderboard_snapshot = models.JSONField(
        null=True,
        blank=True,
        help_text="Per-board rankings captured when the freeze is turned on.",
    )
    design_locked = models.BooleanField(
        default=False,
        help_text=(
            "Freeze the map's look. While on, Designers may not write the design and "
            "the design pages disappear for them."
        ),
    )

    # The run ledger. Elapsed time is accumulated running time, not wall time
    # since kick-off, so pausing the game genuinely pauses every team's timer.
    accumulated_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Seconds the game has spent in the running state, excluding pauses.",
    )
    running_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of the current running stretch; null whenever the game is not running.",
    )
    duration_minutes = models.PositiveSmallIntegerField(
        default=180,
        help_text="Total playing time. The countdown is this minus elapsed; 0 turns it off.",
    )
    # Entry phase: every team answers a short sheet before it may take a spawn.
    entry_question_count = models.PositiveSmallIntegerField(
        default=3, help_text="How many questions land on each team's entry sheet."
    )
    entry_required_correct = models.PositiveSmallIntegerField(
        default=2, help_text="Correct answers needed to unlock the start node."
    )
    entry_grace_minutes = models.PositiveSmallIntegerField(
        default=20,
        help_text="Minutes after kick-off when every team may take a spawn regardless.",
    )
    entry_max_retries = models.PositiveSmallIntegerField(
        default=3,
        help_text=(
            "Extra attempts a team may take on wrongly-answered entry questions, across "
            "the whole sheet. Raise it to be more forgiving; 0 makes every answer final."
        ),
    )
    max_open_attempts = models.PositiveSmallIntegerField(
        default=2,
        help_text=(
            "How many reserved-but-unanswered questions a team may hold at once. "
            "A question the team has answered no longer counts, graded or not; 0 turns the cap off."
        ),
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Stamped the first time status becomes running; anchors the entry grace.",
    )

    class Meta:
        verbose_name = "game settings"
        verbose_name_plural = "game settings"
        # Separate from act_as_mentor on purpose: a mentor grades, a game god
        # starts, pauses and restarts the whole event.
        permissions = [("control_game", "Can start, pause, restart and configure the game")]
        constraints = [
            CheckConstraint(condition=Q(id=1), name="gamesettings_singleton"),
            CheckConstraint(
                condition=Q(entry_required_correct__lte=F("entry_question_count")),
                name="gamesettings_entry_required_within_sheet",
            ),
        ]

    def __str__(self):
        return f"Game settings ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        """Roll the run ledger on every status change, whatever changed it.

        Done here rather than in the view so the admin, a shell session and the
        API all keep the same books.
        """
        previous_status = None
        previous_frozen = None
        if not self._state.adding:
            previous = (
                type(self).objects.filter(pk=self.pk).values("status", "leaderboard_frozen").first()
            )
            if previous is not None:
                previous_status = previous["status"]
                previous_frozen = previous["leaderboard_frozen"]
        freeze_fields = self._roll_leaderboard_freeze(previous_frozen)
        touched = self._roll_clock(previous_status)
        update_fields = kwargs.get("update_fields")
        extra = set(freeze_fields) | set(touched)
        if extra and update_fields is not None:
            kwargs["update_fields"] = {*update_fields, *extra}
        super().save(*args, **kwargs)

    def _roll_leaderboard_freeze(self, previous_frozen) -> tuple[str, ...]:
        """Capture both boards when freeze turns on; drop the snapshot when it turns off."""
        if previous_frozen is None:
            return ()
        if self.leaderboard_frozen and not previous_frozen:
            from teams.leaderboard import snapshot_all_boards

            self.leaderboard_snapshot = snapshot_all_boards()
            return ("leaderboard_snapshot",)
        if not self.leaderboard_frozen and previous_frozen:
            self.leaderboard_snapshot = None
            return ("leaderboard_snapshot",)
        return ()

    def _roll_clock(self, previous_status) -> tuple:
        """Bank the stretch that just ended, and open a new one if now running."""
        if previous_status == self.status:
            # Self-heal a row that claims to be running but never opened a
            # stretch — a hand-edited database, or a migration that added the
            # ledger while the game was already running.
            if self.status == GameStatus.RUNNING and self.running_since is None:
                self.running_since = timezone.now()
                return ("running_since",)
            return ()

        now = timezone.now()
        touched = set()

        if previous_status == GameStatus.RUNNING and self.running_since is not None:
            self.accumulated_seconds += max(0, int((now - self.running_since).total_seconds()))
            self.running_since = None
            touched |= {"accumulated_seconds", "running_since"}

        if self.status == GameStatus.RUNNING:
            self.running_since = now
            touched.add("running_since")
            if self.started_at is None:
                self.started_at = now
                touched.add("started_at")

        return tuple(touched)

    @classmethod
    def load(cls) -> "GameSettings":
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def is_running(self) -> bool:
        return self.status == GameStatus.RUNNING

    @property
    def is_paused(self) -> bool:
        return self.status == GameStatus.PAUSED

    @property
    def elapsed_seconds(self) -> int | None:
        """Running time so far, frozen while paused. None before kick-off."""
        if self.started_at is None:
            return None
        total = self.accumulated_seconds
        if self.is_running and self.running_since is not None:
            total += max(0, int((timezone.now() - self.running_since).total_seconds()))
        return total

    @property
    def duration_seconds(self) -> int:
        return self.duration_minutes * 60

    @property
    def remaining_seconds(self) -> int | None:
        """Time left of the allotted duration, or None when no limit is set."""
        if self.duration_minutes == 0:
            return None
        return max(0, self.duration_seconds - (self.elapsed_seconds or 0))

    @property
    def entry_grace_seconds(self) -> int:
        return self.entry_grace_minutes * 60

    @property
    def entry_grace_remaining_seconds(self) -> int | None:
        """Grace left on the run clock, so a pause freezes it. None before kick-off."""
        elapsed = self.elapsed_seconds
        if elapsed is None:
            return None
        return max(0, self.entry_grace_seconds - elapsed)

    @property
    def entry_grace_ends_at(self):
        """Projected wall-clock end of the grace, for the client's countdown.

        A projection, not a stored deadline: the grace burns run time, not wall
        time, so a paused game has no end to point at and the answer is None
        until it resumes.
        """
        remaining = self.entry_grace_remaining_seconds
        if remaining is None or not self.is_running:
            return None
        return timezone.now() + timedelta(seconds=remaining)

    @property
    def entry_grace_over(self) -> bool:
        remaining = self.entry_grace_remaining_seconds
        return remaining == 0


class Question(models.Model):
    level = models.ForeignKey(
        LevelConfig, on_delete=models.PROTECT, related_name="questions", db_column="level"
    )
    code = models.SlugField(max_length=32, unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, help_text="Markdown")
    attachment = models.FileField(
        upload_to="questions/",
        blank=True,
        validators=[validate_upload_extension, validate_upload_size],
    )
    answer_type = models.CharField(
        max_length=8, choices=AnswerType.choices, default=AnswerType.FILE
    )
    answer_key = models.TextField(
        blank=True,
        help_text="Mentor reference only — never exposed to teams.",
    )
    max_grade = models.PositiveSmallIntegerField(
        default=100,
        help_text="The scale the mentor grades on. Payout is grade/max_grade of the floor reward.",
    )
    mentors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="grading_questions",
        help_text="The mentors who grade submissions for this question. Empty = every mentor queue.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["level", "code"]
        constraints = [
            # Capped at 100 so Occupancy.grade stays inside occ_grade_range.
            CheckConstraint(
                condition=Q(max_grade__gte=1, max_grade__lte=100),
                name="question_max_grade_range",
            ),
        ]
        indexes = [
            models.Index(fields=["level", "is_active"], name="question_level_active_idx"),
        ]

    def clean(self):
        super().clean()
        if not self.title and self.code:
            self.title = self.code

    def __str__(self):
        return self.title or self.code


class TeamQuestion(models.Model):
    """Tracks which questions a team has already been served (no repeats)."""

    team = models.ForeignKey(
        "teams.Team", on_delete=models.CASCADE, related_name="served_questions"
    )
    question = models.ForeignKey(
        Question, on_delete=models.PROTECT, related_name="team_assignments"
    )
    occupancy = models.ForeignKey(
        "Occupancy", on_delete=models.CASCADE, related_name="question_assignments"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=["team", "question"], name="teamquestion_no_repeat"),
        ]
        indexes = [
            models.Index(fields=["team", "question"], name="teamquestion_team_q_idx"),
        ]

    def __str__(self):
        return f"{self.team} served {self.question.code}"


class Submission(models.Model):
    occupancy = models.OneToOneField(Occupancy, on_delete=models.CASCADE, related_name="submission")
    body = models.TextField(blank=True)
    file = models.FileField(
        upload_to="submissions/%Y/%m/",
        blank=True,
        validators=[validate_upload_extension, validate_upload_size],
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submissions",
    )

    class Meta:
        constraints = [
            CheckConstraint(
                condition=~Q(body="", file=""),
                name="submission_has_content",
            ),
        ]

    def __str__(self):
        return f"Submission for {self.occupancy_id}"


class EntryQuestion(models.Model):
    """A pre-game sheet question. Answers are integers, so they grade themselves.

    Deliberately not a `Question`: those hang off an `Occupancy` through
    `TeamQuestion`, and the entry sheet is answered before a team holds any node.
    """

    code = models.SlugField(max_length=32, unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Markdown")
    answer = models.IntegerField(help_text="Never serialised to a team.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        indexes = [models.Index(fields=["is_active"], name="entryquestion_active_idx")]

    def __str__(self):
        return self.title or self.code


class EntryAttemptQuerySet(models.QuerySet):
    def current(self):
        """The sheet as it stands now — superseded tries are history."""
        return self.filter(superseded_at__isnull=True)


class EntryAttempt(models.Model):
    """One try at one question on one team's entry sheet.

    A wrong answer is not the end of that question: the team may take another
    run at *the same question* while its retry budget lasts
    (`GameSettings.entry_max_retries`). Retrying supersedes this row and opens a
    fresh one for the same question at the same position, rather than clearing
    the columns — append-and-soft-retire, the same shape as `Occupancy`, so
    every guess a team made stays on the record.
    """

    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, related_name="entry_attempts")
    question = models.ForeignKey(EntryQuestion, on_delete=models.PROTECT, related_name="attempts")
    position = models.PositiveSmallIntegerField(help_text="Slot on the sheet, 1-based.")

    answer = models.IntegerField(null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    superseded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the team spent a retry and started a fresh try at this question.",
    )

    objects = EntryAttemptQuerySet.as_manager()

    class Meta:
        ordering = ["team", "position"]
        constraints = [
            # Scoped to current rows: retrying stacks tries at the same question,
            # but only one of them is ever live.
            UniqueConstraint(
                fields=["team", "question"],
                condition=Q(superseded_at__isnull=True),
                name="entryattempt_no_repeat",
            ),
            UniqueConstraint(
                fields=["team", "position"],
                condition=Q(superseded_at__isnull=True),
                name="entryattempt_one_per_position",
            ),
            CheckConstraint(condition=Q(position__gte=1), name="entryattempt_position_positive"),
            # Answering writes all three columns at once; nothing half-recorded.
            CheckConstraint(
                condition=(
                    Q(answered_at__isnull=True, answer__isnull=True, is_correct__isnull=True)
                    | Q(
                        answered_at__isnull=False,
                        answer__isnull=False,
                        is_correct__isnull=False,
                    )
                ),
                name="entryattempt_answer_recorded_together",
            ),
            # Only a wrong answer is retryable, so a superseded row is always one.
            CheckConstraint(
                condition=Q(superseded_at__isnull=True) | Q(is_correct=False),
                name="entryattempt_only_wrong_is_superseded",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "is_correct"], name="entryattempt_team_correct_idx"),
        ]

    def __str__(self):
        return f"{self.team} sheet #{self.position}: {self.question.code}"

    @property
    def is_answered(self) -> bool:
        return self.answered_at is not None

    @property
    def is_superseded(self) -> bool:
        return self.superseded_at is not None


class Neighborhood(models.Model):
    """One of the map's eight pizza slices.

    Membership is geometry, not data: a node belongs to sector
    `floor(theta / 45)`, which the frontend computes from the map JSON. This row
    only says what that sector is called and how it is painted, which is what a
    Designer is allowed to change.
    """

    index = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=64)
    theme = models.CharField(max_length=16, choices=NeighborhoodTheme.choices)
    color = models.CharField(
        max_length=7,
        validators=[RegexValidator(r"^#[0-9a-f]{6}$", "Color must be a lowercase #rrggbb hex.")],
    )

    class Meta:
        ordering = ["index"]
        constraints = [
            CheckConstraint(
                condition=Q(index__gte=0, index__lt=SECTOR_COUNT),
                name="neighborhood_index_range",
            ),
        ]

    def __str__(self):
        return f"{self.index}: {self.name}"


class MapDesign(models.Model):
    """The handful of map-wide knobs a Designer turns. Singleton, like GameSettings."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    road_style = models.CharField(
        max_length=12, choices=RoadStyle.choices, default=RoadStyle.STRAIGHT
    )
    tint_strength = models.PositiveSmallIntegerField(
        default=DEFAULT_TINT_STRENGTH,
        help_text="How strongly each sector is washed with its colour, 0–100.",
    )
    halo_strength = models.PositiveSmallIntegerField(
        default=DEFAULT_HALO_STRENGTH,
        help_text="Opacity of the neighbourhood ring around every node, 0–100.",
    )

    class Meta:
        verbose_name = "map design"
        verbose_name_plural = "map design"
        # Distinct from both mentor and game-god rights: a Designer changes how
        # the board looks, never who holds what or whether the clock runs.
        permissions = [("design_map", "Can edit the map's look")]
        constraints = [
            CheckConstraint(condition=Q(id=1), name="mapdesign_singleton"),
            CheckConstraint(condition=Q(tint_strength__lte=100), name="mapdesign_tint_range"),
            CheckConstraint(condition=Q(halo_strength__lte=100), name="mapdesign_halo_range"),
        ]

    def __str__(self):
        return "Map design"

    @classmethod
    def load(cls) -> "MapDesign":
        return cls.objects.get_or_create(pk=1)[0]
