from django.core.validators import RegexValidator
from django.db import models
from django.db.models import CheckConstraint, Prefetch, Q, UniqueConstraint


class BalanceReason(models.TextChoices):
    INITIAL = "initial", "موجودی اولیه"
    ENTRY = "entry", "رزرو خانه"
    GRADE = "grade", "نمره خانه"


def active_holdings():
    from game.models import Occupancy

    return Occupancy.objects.active().select_related("node").order_by("node__code")


class TeamQuerySet(models.QuerySet):
    def with_holdings(self):
        """Prefetch each team's active occupancies so `.holdings` costs one query."""
        return self.prefetch_related(
            Prefetch("occupancies", queryset=active_holdings(), to_attr="_holdings")
        )


class Team(models.Model):
    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=64)

    balance = models.PositiveIntegerField(default=0)

    # Claimed from a start node; empty until the team enters one.
    color = models.CharField(
        max_length=7,
        null=True,
        blank=True,
        validators=[RegexValidator(r"^#[0-9a-f]{6}$", "Color must be a lowercase #rrggbb hex.")],
    )

    # Spawn sequence for teams based on entry question solved
    draft_order = models.PositiveSmallIntegerField(null=True, blank=True, unique=True)

    # Duel cooldown is per team, not per holding: a team with several houses
    # must not be challengeable once per house inside the same window.
    last_duel_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = TeamQuerySet.as_manager()

    class Meta:
        ordering = ["code"]
        constraints = [
            CheckConstraint(
                condition=Q(draft_order__isnull=True) | Q(draft_order__gte=1),
                name="team_draft_order_positive",
            ),
            UniqueConstraint(
                fields=["color"],
                condition=Q(color__isnull=False),
                name="team_color_unique_when_set",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def holdings(self):
        """Nodes the team holds right now. Queries unless with_holdings() prefetched."""
        if hasattr(self, "_holdings"):
            return self._holdings
        return active_holdings().filter(team=self)


class ItemType(models.TextChoices):
    FAKE_DOCUMENT = "fake_document", "سند جعلی"
    GEL = "gel", "گل"
    GILARI_100 = "gilari_100", "۱۰۰ گیلاری"


class TeamItem(models.Model):
    """One stack of a given item type in a team's inventory."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=16, choices=ItemType.choices)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["team", "item_type"]
        constraints = [
            UniqueConstraint(fields=["team", "item_type"], name="teamitem_one_per_type"),
        ]

    def __str__(self) -> str:
        return f"{self.team} {self.get_item_type_display()} ×{self.quantity}"


class BalanceEvent(models.Model):
    """One row per wallet change so the team panel can replay the score log."""

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="balance_events")
    delta = models.IntegerField()
    balance_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=16, choices=BalanceReason.choices)
    detail = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["team", "created_at"], name="balance_event_team_time"),
        ]

    def __str__(self) -> str:
        sign = "+" if self.delta >= 0 else ""
        return f"{self.team_id} {sign}{self.delta} ({self.reason})"
