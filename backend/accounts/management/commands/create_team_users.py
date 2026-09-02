"""Create one login per team so teams can play their own moves online.

Mentors used to be the only accounts; each team now needs its own username and
password. One User per Team, linked through the existing accounts.User.team FK,
so no other wiring is needed. Idempotent: an existing account is left alone
unless --reset is passed, and re-running --fund only tops up teams still at 0.
"""

import csv
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.crypto import get_random_string

from game.models import GameSettings
from teams.ledger import apply_balance_change
from teams.models import BalanceReason, Team

User = get_user_model()

# No 0/O/1/I/l — read aloud or typed off a slip, they're the passwords most
# often mistyped.
PASSWORD_CHARS = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_password() -> str:
    return get_random_string(10, PASSWORD_CHARS)


class Command(BaseCommand):
    help = "Create or reset one login per team, and optionally fund starting balances."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Re-roll the password of teams that already have an account.",
        )
        parser.add_argument(
            "--fund",
            action="store_true",
            help="Set balance to GameSettings.initial_balance for teams still at 0.",
        )
        parser.add_argument(
            "--csv",
            type=Path,
            default=None,
            help="Also write code,name,username,password to this file.",
        )

    def handle(self, *args, **options):
        rows = []
        created = reset_count = skipped = 0

        with transaction.atomic():
            for team in Team.objects.order_by("code"):
                user = team.members.order_by("pk").first()

                if user is None:
                    conflict = User.objects.filter(username=team.code).first()
                    if conflict is not None:
                        raise CommandError(
                            f"Username '{team.code}' is already taken by user id "
                            f"{conflict.pk}; rename it before running this command."
                        )
                    password = _generate_password()
                    user = User(username=team.code, team=team)
                    user.set_password(password)
                    user.save()
                    rows.append((team.code, team.name, user.username, password))
                    created += 1
                elif options["reset"]:
                    password = _generate_password()
                    user.set_password(password)
                    user.save(update_fields=["password"])
                    rows.append((team.code, team.name, user.username, password))
                    reset_count += 1
                else:
                    skipped += 1

            funded = 0
            if options["fund"]:
                initial_balance = GameSettings.load().initial_balance
                for team in Team.objects.filter(balance=0):
                    apply_balance_change(
                        team,
                        initial_balance,
                        reason=BalanceReason.INITIAL,
                    )
                    funded += 1

        writer = csv.writer(self.stdout)
        writer.writerow(["code", "name", "username", "password"])
        for row in rows:
            writer.writerow(row)

        if options["csv"]:
            with options["csv"].open("w", newline="", encoding="utf-8") as fh:
                file_writer = csv.writer(fh)
                file_writer.writerow(["code", "name", "username", "password"])
                file_writer.writerows(rows)

        summary = f"{created} created, {reset_count} reset, {skipped} unchanged."
        if options["fund"]:
            summary += f" {funded} team(s) funded."
        self.stdout.write(self.style.SUCCESS(summary))
