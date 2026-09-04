"""Duels: one team challenging another for a floor it already owns.

A duel is not played on the board. The two teams meet in a Skyroom meeting run
by a judge, play whatever game the judge sets, and the judge reports who won.
Everything the server owns is therefore the *bookkeeping* around that meeting —
who is fighting whom, over which floor, for how much, in whose room — plus the
settlement once a winner comes back.

Two models:

`Room` is the meeting itself: a Skyroom link and the person who runs it. Rooms
are created by organisers in admin, never by players, and they are the unit the
judge queue rotates over — picking a judge *is* picking their room, because a
judge without a link cannot host anything.

`Duel` is one challenge. It is closed exactly once, by the judge naming a
winner; there is no draw path and no server-side timer. The five-minute no-show
rule from the rules sheet is run by the judge in the room, not by this app — an
absent team is simply not named as the winner.

Ownership and money both move at that moment, in `services.resolve_duel`.
"""

from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint


class DuelStatus(models.TextChoices):
    OPEN = "open", "باز"
    CLOSED = "closed", "بسته"


class Room(models.Model):
    """A Skyroom meeting and the judge who runs it.

    `last_assigned_at` is the whole of the circular queue: rooms are handed out
    least-recently-used first, with never-used rooms ahead of everything, so a
    judge who has just taken a duel goes to the back of the line. Clearing it
    puts a room back at the front, which is what an organiser adding a room
    mid-event wants.

    `is_active` rather than deleting: `Duel.room` is PROTECT, so a room that has
    ever hosted a duel cannot be removed without taking its history with it.
    Unticking takes the room out of rotation and leaves the record intact.
    """

    name = models.CharField(max_length=64, help_text="How organisers recognise this room.")
    link = models.URLField(
        max_length=500,
        help_text="The Skyroom meeting URL. Only the two teams and the judge ever see it.",
    )
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="duel_rooms",
        help_text="The judge who runs this room. Must hold judge_duel.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Untick to take the room out of rotation without losing its duels.",
    )
    last_assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Stamped when the room is handed a duel. Never-used rooms are picked first.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            UniqueConstraint(fields=["link"], name="room_link_unique"),
        ]
        indexes = [
            models.Index(
                fields=["last_assigned_at"],
                condition=Q(is_active=True),
                name="room_rotation_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.mentor})"


class DuelQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status=DuelStatus.OPEN)

    def closed(self):
        return self.filter(status=DuelStatus.CLOSED)

    def for_team(self, team):
        return self.filter(Q(attacker=team) | Q(attacked=team))

    def detailed(self):
        """Everything a duel card renders, in one query."""
        return self.select_related(
            "attacker",
            "attacked",
            "winner",
            "loser",
            "node",
            "room",
            "mentor",
            "target",
        )


class Duel(models.Model):
    """One challenge over one floor of one building.

    The contested floor is pinned by `target`, not merely by `node` and `floor`:
    the attacker names *which team on which floor* it is coming for, and that
    Occupancy row is what gets released if the defender loses. `floor` and
    `stake` are snapshots, so a closed duel still reads correctly once the
    occupancy has been released and the price table has been retuned.
    """

    attacker = models.ForeignKey(
        "teams.Team", on_delete=models.PROTECT, related_name="duels_started"
    )
    attacked = models.ForeignKey(
        "teams.Team", on_delete=models.PROTECT, related_name="duels_received"
    )

    node = models.ForeignKey("game.Node", on_delete=models.PROTECT, related_name="duels")
    target = models.ForeignKey(
        "game.Occupancy",
        on_delete=models.PROTECT,
        related_name="duels",
        help_text="The defender's seat being contested. Handed to the attacker on a loss.",
    )
    floor = models.PositiveSmallIntegerField(help_text="Snapshot of the contested floor.")
    stake = models.PositiveIntegerField(
        help_text=(
            "What the attacker paid up front. Refunded on a win, paid to the defender on a loss."
        )
    )

    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="duels")
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="judged_duels",
        help_text="Snapshot of the room's judge, so repointing a room never rewrites history.",
    )

    status = models.CharField(max_length=6, choices=DuelStatus.choices, default=DuelStatus.OPEN)
    winner = models.ForeignKey(
        "teams.Team", null=True, blank=True, on_delete=models.PROTECT, related_name="duels_won"
    )
    loser = models.ForeignKey(
        "teams.Team", null=True, blank=True, on_delete=models.PROTECT, related_name="duels_lost"
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resolved_duels",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = DuelQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        # Judging is its own job, the way announcing is: running a meeting and
        # calling a winner has nothing to do with grading questions or driving
        # the clock. Backed by the DuelMentors group seeded in 0002.
        permissions = [("judge_duel", "Can judge duels")]
        constraints = [
            CheckConstraint(
                condition=~Q(attacker=F("attacked")),
                name="duel_two_distinct_teams",
            ),
            # An open duel has no result yet; a closed one has a whole result.
            CheckConstraint(
                condition=(
                    Q(
                        status=DuelStatus.OPEN,
                        winner__isnull=True,
                        loser__isnull=True,
                        resolved_at__isnull=True,
                    )
                    | Q(
                        status=DuelStatus.CLOSED,
                        winner__isnull=False,
                        loser__isnull=False,
                        resolved_at__isnull=False,
                    )
                ),
                name="duel_status_consistent",
            ),
            CheckConstraint(
                condition=(
                    Q(winner__isnull=True) | Q(winner=F("attacker")) | Q(winner=F("attacked"))
                ),
                name="duel_winner_is_participant",
            ),
            CheckConstraint(
                condition=(Q(loser__isnull=True) | Q(loser=F("attacker")) | Q(loser=F("attacked"))),
                name="duel_loser_is_participant",
            ),
            CheckConstraint(
                condition=Q(winner__isnull=True) | ~Q(winner=F("loser")),
                name="duel_winner_is_not_loser",
            ),
            # One live duel per team, in *either* role — the rules sheet counts
            # hunter and hunted together. That spans two columns, which no
            # partial unique can express, so `services.request_duel` enforces it
            # under a row lock. These two are the net underneath, each catching
            # one half of it.
            UniqueConstraint(
                fields=["attacker"],
                condition=Q(status=DuelStatus.OPEN),
                name="duel_one_open_per_attacker",
            ),
            UniqueConstraint(
                fields=["attacked"],
                condition=Q(status=DuelStatus.OPEN),
                name="duel_one_open_per_attacked",
            ),
            # Two attackers must not be mid-duel over the same seat: the second
            # win would arrive to find the floor already gone.
            UniqueConstraint(
                fields=["target"],
                condition=Q(status=DuelStatus.OPEN),
                name="duel_one_open_per_target",
            ),
        ]
        indexes = [
            models.Index(
                fields=["mentor"],
                condition=Q(status=DuelStatus.OPEN),
                name="duel_open_by_mentor_idx",
            ),
        ]

    def __str__(self):
        return f"{self.attacker} vs {self.attacked} @ {self.node_id} floor {self.floor}"

    @property
    def is_open(self) -> bool:
        return self.status == DuelStatus.OPEN

    def opponent_of(self, team):
        """The other side, or None when `team` is not in this duel."""
        if team.pk == self.attacker_id:
            return self.attacked
        if team.pk == self.attacked_id:
            return self.attacker
        return None
