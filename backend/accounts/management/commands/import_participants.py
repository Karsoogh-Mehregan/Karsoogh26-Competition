"""Import teams and one login per participant from the merged roster CSV.

The CSV is produced by `scripts/build_participants_csv.py`, which joins the
organisers' roster spreadsheet to the registration export. Columns read here:
`board`, `team_code`, `team_name`, `username`, `first_name`, `last_name`; every
other column in that file is join provenance and is ignored.

The password is the username, as issued by the registration platform. Rows with
an empty `username` are the ones the join could not resolve and are skipped with
a warning — the roster is imported around them rather than being blocked by them.

Idempotent: an existing team keeps its name and board, and an existing account
keeps its password unless `--reset-passwords` is passed.
"""

import csv
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.boards import Board
from teams.models import Team

User = get_user_model()

REQUIRED_COLUMNS = {"board", "team_code", "team_name", "username"}


class Command(BaseCommand):
    help = "Create teams and per-participant logins from the merged roster CSV."

    def add_arguments(self, parser):
        parser.add_argument("--csv", type=Path, required=True)
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset an existing account's password back to its username.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change and roll back.",
        )

    def handle(self, *args, **options):
        path: Path = options["csv"]
        if not path.exists():
            raise CommandError(f"{path} does not exist.")

        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        if not rows:
            raise CommandError(f"{path} has no data rows.")
        missing = REQUIRED_COLUMNS - set(rows[0])
        if missing:
            raise CommandError(f"{path} is missing columns: {', '.join(sorted(missing))}")

        teams_created = users_created = users_reset = skipped_no_username = existing = 0
        conflicts = []

        with transaction.atomic():
            teams: dict[str, Team] = {}
            for line, row in enumerate(rows, start=2):
                code = row["team_code"].strip()
                board = row["board"].strip()
                if not code:
                    raise CommandError(f"line {line}: empty team_code")
                if board not in Board.values:
                    raise CommandError(f"line {line}: unknown board '{board}'")

                team = teams.get(code)
                if team is None:
                    team, created = Team.objects.get_or_create(
                        code=code,
                        defaults={"name": row["team_name"].strip() or code, "board": board},
                    )
                    teams[code] = team
                    teams_created += created
                    if not created and team.board != board:
                        raise CommandError(
                            f"line {line}: team '{code}' is already on board "
                            f"'{team.board}', CSV says '{board}'"
                        )

                username = row["username"].strip()
                if not username:
                    skipped_no_username += 1
                    self.stderr.write(
                        f"line {line}: no username for "
                        f"'{row.get('display_name', '').strip()}' in {code} — skipped"
                    )
                    continue

                user = User.objects.filter(username=username).first()
                if user is None:
                    user = User(
                        username=username,
                        team=team,
                        first_name=row.get("first_name", "").strip(),
                        last_name=row.get("last_name", "").strip(),
                    )
                    user.set_password(username)
                    user.save()
                    users_created += 1
                    continue

                existing += 1
                if user.team_id is not None and user.team_id != team.pk:
                    conflicts.append(
                        f"line {line}: user '{username}' already belongs to team "
                        f"'{user.team.code}', CSV says '{code}' — left alone"
                    )
                    continue

                fields = []
                if user.team_id is None:
                    user.team = team
                    fields.append("team")
                if options["reset_passwords"]:
                    user.set_password(username)
                    fields.append("password")
                    users_reset += 1
                if fields:
                    user.save(update_fields=fields)

            if options["dry_run"]:
                transaction.set_rollback(True)

        for line in conflicts:
            self.stderr.write(self.style.WARNING(line))

        summary = (
            f"teams created: {teams_created}  users created: {users_created}  "
            f"users already present: {existing}  passwords reset: {users_reset}  "
            f"rows skipped without a username: {skipped_no_username}"
        )
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING(f"DRY RUN, rolled back — {summary}"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
