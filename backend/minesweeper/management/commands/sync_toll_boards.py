"""Provision (and optionally retune) the Minesweeper board behind every toll gate.

Run it after `import_graph` on a database that predates the gates, or whenever
organisers want every gate on one difficulty. `import_graph` calls the same
service itself, so a normal import needs nothing extra.
"""

from django.core.management.base import BaseCommand, CommandError

from minesweeper.exceptions import InvalidDifficulty
from minesweeper.models import DifficultyConfig
from minesweeper.services import ensure_toll_boards


class Command(BaseCommand):
    help = "Create a Minesweeper board for every toll node, and optionally set its difficulty."

    def add_arguments(self, parser):
        parser.add_argument(
            "--difficulty",
            help=(
                "Apply this difficulty to every toll gate, existing rows included. "
                "Omit to only fill in gates that have no board yet."
            ),
        )

    def handle(self, *args, **options):
        try:
            counts = ensure_toll_boards(difficulty=options["difficulty"])
        except InvalidDifficulty as exc:
            known = ", ".join(DifficultyConfig.objects.values_list("key", flat=True))
            raise CommandError(f"{exc} Configured difficulties: {known or 'none'}.") from exc

        total = sum(counts.values())
        if total == 0:
            self.stdout.write(
                self.style.WARNING("No toll nodes on the map. Run `manage.py import_graph` first.")
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                "Toll boards: {created} created, {updated} retuned, {unchanged} unchanged.".format(
                    **counts
                )
            )
        )
