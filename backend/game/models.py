from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint
from django.utils import timezone

from .validators import validate_upload_extension, validate_upload_size

MAX_CAPACITY = 3


def _round_half_up(value: Decimal) -> int:
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class Level(models.TextChoices):
    SPAWN = "spawn", "شروع"
    EASY = "easy", "آسان"
    MEDIUM = "medium", "متوسط"
    HARD = "hard", "سخت"
    TOLL = "toll", "عوارضی"


class ReleaseReason(models.TextChoices):
    ZERO_GRADE = "zero_grade", "نمره صفر"
    EXPIRED = "expired", "منقضی شد"
    DUEL_LOST = "duel_lost", "باخت دوئل"
    BOUGHT_OUT = "bought_out", "خریداری شد"


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

    networth_base = models.IntegerField(default=0)
    networth_factor = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    duel_factor = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("2"))
    buyout_factor = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("4"))

    class Meta:
        verbose_name = "level config"
        verbose_name_plural = "level configs"
        constraints = [
            CheckConstraint(
                condition=Q(capacity__gte=1, capacity__lte=MAX_CAPACITY),
                name="levelconfig_capacity_range",
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

    @property
    def networth(self) -> int:
        """End-of-game value of holding this floor."""
        return self.level.networth_base + _round_half_up(self.level.networth_factor * self.points)

    @property
    def duel_cost(self) -> int:
        return _round_half_up(self.level.duel_factor * self.points)

    @property
    def buyout_cost(self) -> int:
        return _round_half_up(self.level.buyout_factor * self.points)


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
    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=64, blank=True)
    level = models.ForeignKey(
        LevelConfig, on_delete=models.PROTECT, related_name="nodes", db_column="level"
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name or self.code


class Edge(models.Model):
    """A link between two nodes. Directed ones run a -> b; undirected ones are
    normalised to a.id < b.id, so each unordered pair stores once."""

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
                condition=Q(released_at__isnull=True),
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

    attempt_ttl_minutes = models.PositiveSmallIntegerField(default=15)
    duel_cooldown_minutes = models.PositiveSmallIntegerField(default=10)
    duel_deadline_minutes = models.PositiveSmallIntegerField(default=15)
    initial_balance = models.PositiveIntegerField(default=500)
    status = models.CharField(
        max_length=12, choices=GameStatus.choices, default=GameStatus.NOT_STARTED
    )

    class Meta:
        verbose_name = "game settings"
        verbose_name_plural = "game settings"
        constraints = [CheckConstraint(condition=Q(id=1), name="gamesettings_singleton")]

    def __str__(self):
        return f"Game settings ({self.get_status_display()})"

    @classmethod
    def load(cls) -> "GameSettings":
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def is_running(self) -> bool:
        return self.status == GameStatus.RUNNING

    @property
    def is_paused(self) -> bool:
        return self.status == GameStatus.PAUSED


class Question(models.Model):
    level = models.ForeignKey(
        LevelConfig, on_delete=models.PROTECT, related_name="questions", db_column="level"
    )
    code = models.SlugField(max_length=32, unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Markdown")
    attachment = models.FileField(
        upload_to="questions/",
        blank=True,
        validators=[validate_upload_extension, validate_upload_size],
    )
    answer_type = models.CharField(max_length=8, choices=AnswerType.choices)
    answer_key = models.TextField(
        blank=True,
        help_text="Mentor reference only — never exposed to teams.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["level", "code"]
        indexes = [
            models.Index(fields=["level", "is_active"], name="question_level_active_idx"),
        ]

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
