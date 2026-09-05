"""Pay the end-of-game networth of every held floor into the teams' wallets.

Run once, after the game is over. A team that already carries a `networth`
balance event is skipped, so a second run pays nothing twice.
"""

from django.core.management.base import BaseCommand

from core.boards import Board
from game.services.networth import plan_settlement, settle_networth


class Command(BaseCommand):
    help = "Credit each team the networth of the floors it still holds."

    def add_arguments(self, parser):
        parser.add_argument("--board", choices=Board.values, help="Limit to one contest.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        board = options["board"]

        if options["dry_run"]:
            total = 0
            for entry in plan_settlement(board):
                if entry.already_settled:
                    self.stdout.write(
                        self.style.WARNING(f"skip   {entry.team.code} already settled")
                    )
                    continue
                if entry.amount == 0:
                    continue
                total += entry.amount
                self.stdout.write(
                    f"pay    {entry.team.code} +{entry.amount} ({entry.floors} floors)"
                )
            self.stdout.write(self.style.SUCCESS(f"[dry-run] {total} would be paid."))
            return

        paid = settle_networth(board)
        for entry in paid:
            self.stdout.write(f"paid   {entry.team.code} +{entry.amount} ({entry.floors} floors)")
        total = sum(entry.amount for entry in paid)
        self.stdout.write(self.style.SUCCESS(f"{len(paid)} teams settled, {total} paid."))
