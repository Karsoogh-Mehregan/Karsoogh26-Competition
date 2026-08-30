from django.core.validators import RegexValidator
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint


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
