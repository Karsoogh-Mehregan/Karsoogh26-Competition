from django.db import models
from django.db.models import CheckConstraint, Prefetch, Q


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
        ]

    def __str__(self):
        return self.name

    @property
    def holdings(self):
        """Nodes the team holds right now. Queries unless with_holdings() prefetched."""
        if hasattr(self, "_holdings"):
            return self._holdings
        return active_holdings().filter(team=self)
