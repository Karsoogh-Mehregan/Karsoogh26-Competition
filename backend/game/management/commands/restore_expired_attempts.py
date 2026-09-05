"""Give back attempts whose clock ran out while the game was stopped.

`Occupancy.expires_at` is wall-clock, so pausing the game does not pause a
team's question timer: a stop of an hour burns an hour of every open attempt.
This command reopens those attempts and restarts their clock.

It touches only attempts that expired inside a window (default: the last hour)
and never a graded one, a submitted one, or a seat another team has taken since.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.boards import Board
from game.models import Occupancy, ReleaseReason


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

        base = Occupancy.objects.select_related("node__level", "team").filter(
            question_id__isnull=False,
            grade__isnull=True,
            floor__isnull=True,
            submission__isnull=True,
            expires_at__isnull=False,
            expires_at__lte=now,
            expires_at__gte=cutoff,
        )
        if options["board"]:
            base = base.filter(team__board=options["board"])
        if options["team"]:
            base = base.filter(team__code=options["team"])

        swept = base.filter(released_at__isnull=False, release_reason=ReleaseReason.EXPIRED)
        pending = base.filter(released_at__isnull=True)

        restored, reclocked, skipped = [], [], []

        with transaction.atomic():
            for occ in pending.select_for_update():
                occ.expires_at = now + timedelta(
                    minutes=minutes or occ.node.level.attempt_ttl_minutes
                )
                if not options["dry_run"]:
                    occ.save(update_fields=["expires_at"])
                reclocked.append(occ)

            for occ in swept.select_for_update():
                conflict = self._conflict(occ)
                if conflict:
                    skipped.append((occ, conflict))
                    continue
                occ.released_at = None
                occ.release_reason = ""
                occ.expires_at = now + timedelta(
                    minutes=minutes or occ.node.level.attempt_ttl_minutes
                )
                if not options["dry_run"]:
                    occ.save(update_fields=["released_at", "release_reason", "expires_at"])
                restored.append(occ)

            if options["dry_run"]:
                transaction.set_rollback(True)

        for occ in reclocked:
            self.stdout.write(f"re-clocked  {occ.team.code} {occ.node.code} slot {occ.slot}")
        for occ in restored:
            self.stdout.write(f"restored    {occ.team.code} {occ.node.code} slot {occ.slot}")
        for occ, reason in skipped:
            self.stdout.write(
                self.style.WARNING(f"skipped     {occ.team.code} {occ.node.code}: {reason}")
            )

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}{len(reclocked)} re-clocked, {len(restored)} restored, "
                f"{len(skipped)} skipped."
            )
        )

    def _conflict(self, occ: Occupancy) -> str | None:
        active = Occupancy.objects.active().exclude(pk=occ.pk)
        if active.filter(node_id=occ.node_id, slot=occ.slot).exists():
            return "slot taken since"
        if occ.floor is not None and active.filter(node_id=occ.node_id, floor=occ.floor).exists():
            return "floor taken since"
        if active.filter(team_id=occ.team_id, node_id=occ.node_id, source=occ.source).exists():
            return "team already holds this node"
        return None
