"""Give back attempts whose clock ran out while the game was stopped.

`Occupancy.expires_at` is wall-clock, so pausing the game does not pause a
team's question timer: a stop of an hour burns an hour of every open attempt.
This command reopens those attempts and restarts their clock.

It touches only attempts that expired inside a window (default: the last hour)
and never a graded one, a submitted one, or a seat another team has taken since.
The same reopen lives on the Occupancy admin as an action, for hand-picked rows.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from core.boards import Board
from game.models import Occupancy, ReleaseReason
from game.services.attempts import reopen_attempts


class Command(BaseCommand):
    help = "Reopen and re-clock attempts that expired while the game was stopped."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since-minutes",
            type=int,
            default=60,
            help="Only attempts that expired this many minutes ago or later. Default 60.",
        )
        parser.add_argument(
            "--minutes",
            type=int,
            default=None,
            help="Fresh clock in minutes. Default: the node level's attempt_ttl_minutes.",
        )
        parser.add_argument("--board", choices=Board.values, help="Limit to one contest.")
        parser.add_argument("--team", help="Limit to one team code.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        since = options["since_minutes"]
        minutes = options["minutes"]
        if since < 0:
            raise CommandError("--since-minutes cannot be negative.")
        if minutes is not None and minutes <= 0:
            raise CommandError("--minutes must be positive.")

        now = timezone.now()
        cutoff = now - timedelta(minutes=since)

        targets = Occupancy.objects.select_related("node__level", "team").filter(
            Q(released_at__isnull=True) | Q(release_reason=ReleaseReason.EXPIRED),
            question_id__isnull=False,
            grade__isnull=True,
            floor__isnull=True,
            submission__isnull=True,
            expires_at__lte=now,
            expires_at__gte=cutoff,
        )
        if options["board"]:
            targets = targets.filter(team__board=options["board"])
        if options["team"]:
            targets = targets.filter(team__code=options["team"])

        if options["dry_run"]:
            for occupancy in targets:
                state = "restore" if occupancy.released_at else "re-clock"
                self.stdout.write(f"{state:10} {occupancy.team.code} {occupancy.node.code}")
            self.stdout.write(self.style.SUCCESS(f"[dry-run] {targets.count()} would reopen."))
            return

        reopened, skipped = reopen_attempts(list(targets), minutes=minutes)
        for occupancy in reopened:
            self.stdout.write(f"reopened  {occupancy.team.code} {occupancy.node.code}")
        for occupancy, reason in skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"skipped   {occupancy.team.code} {occupancy.node.code}: {reason}"
                )
            )
        self.stdout.write(self.style.SUCCESS(f"{len(reopened)} reopened, {len(skipped)} skipped."))
