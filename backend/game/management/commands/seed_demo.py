"""Stand up a playable demo: teams, their logins, a mentor, and the entry sheet.

Development and rehearsal only — it starts the game and funds every team. The
real event creates teams from the registration list and uses
`create_team_users` for the logins.

    uv run manage.py seed_demo --teams 4 --password demo1234
    uv run manage.py seed_demo --teams 8 --csv demo-logins.csv

Requires the map: run `uv run manage.py import_graph` first, or the start
nodes the teams need to claim will not exist.
"""

import csv

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.management.commands.create_team_users import _generate_password
from game.models import EntryQuestion, GameSettings, GameStatus, Node
from teams.models import Team

User = get_user_model()

MENTOR_GROUP = "Mentors"
MENTOR_USERNAME = "mentor"

# Latin codes keep usernames typable; the Persian name is what the SPA shows.
TEAM_NAMES = [
    ("shahin", "شاهین"),
    ("simorgh", "سیمرغ"),
    ("homa", "هما"),
    ("oghab", "عقاب"),
    ("alborz", "البرز"),
    ("zagros", "زاگرس"),
    ("kavir", "کویر"),
    ("darya", "دریا"),
    ("setare", "ستاره"),
    ("tufan", "طوفان"),
    ("azarakhsh", "آذرخش"),
    ("kuhsar", "کوهسار"),
]


def _team_spec(index: int) -> tuple[str, str]:
    """Named teams first, then numbered ones so --teams can exceed the list."""
    if index < len(TEAM_NAMES):
        return TEAM_NAMES[index]
    number = index + 1
    return f"team-{number}", f"تیم {number}"


class Command(BaseCommand):
    help = "Seed demo teams, logins, a mentor and the entry-question pool."

    def add_arguments(self, parser):
        parser.add_argument("--teams", type=int, default=4, help="How many teams (default 4).")
        parser.add_argument(
            "--password",
            default=None,
            help="One password for every demo account. Omit to generate one per user.",
        )
        parser.add_argument(
            "--csv",
            default=None,
            help="Also write username,password,role,team to this file.",
        )
        parser.add_argument(
            "--no-start",
            action="store_true",
            help="Leave GameSettings.status alone instead of setting it to running.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["teams"]
        if count < 1:
            self.stderr.write(self.style.ERROR("--teams must be at least 1."))
            return

        call_command("seed_entry_questions", verbosity=0)

        settings_row = GameSettings.load()
        rows = []

        for index in range(count):
            code, name = _team_spec(index)
            team, _ = Team.objects.get_or_create(
                code=code, defaults={"name": name, "balance": settings_row.initial_balance}
            )
            # A demo reseed puts every team back on the same footing, spent
            # balance included. The real event funds once, via create_team_users.
            if team.balance != settings_row.initial_balance:
                team.balance = settings_row.initial_balance
                team.save(update_fields=["balance"])
            rows.append(self._account(code, team, options["password"], role="team"))

        rows.append(self._account(MENTOR_USERNAME, None, options["password"], role="mentor"))

        if not options["no_start"]:
            # Clear the stamp first so save() re-anchors it now and the entry
            # grace window restarts with the demo rather than an older run.
            settings_row.status = GameStatus.RUNNING
            settings_row.started_at = None
            settings_row.save(update_fields=["status", "started_at"])

        self._report(rows, settings_row, options["csv"])

    def _account(self, username: str, team: Team | None, password: str | None, *, role: str):
        """Create the login if missing; always set the password when one is given."""
        user, created = User.objects.get_or_create(
            username=username, defaults={"team": team, "is_staff": role == "mentor"}
        )
        if team is not None and user.team_id != team.pk:
            user.team = team
            user.save(update_fields=["team"])
        if role == "mentor":
            user.groups.add(Group.objects.get(name=MENTOR_GROUP))

        if password is not None:
            user.set_password(password)
            user.save(update_fields=["password"])
            shown = password
        elif created:
            shown = _generate_password()
            user.set_password(shown)
            user.save(update_fields=["password"])
        else:
            shown = "(unchanged)"

        return {
            "username": username,
            "password": shown,
            "role": role,
            "team_code": team.code if team else "-",
            "team_name": team.name if team else "-",
        }

    def _report(self, rows, settings_row, csv_path):
        # Codes only in the console table: a Windows terminal on cp1252 raises
        # UnicodeEncodeError on the Persian names. The CSV is UTF-8 and keeps them.
        width = max(len("username"), *(len(row["username"]) for row in rows))
        self.stdout.write("")
        self.stdout.write(f"{'username'.ljust(width)}  password      role    team")
        self.stdout.write(f"{'-' * width}  ------------  ------  ------")
        for row in rows:
            self.stdout.write(
                f"{row['username'].ljust(width)}  {row['password'].ljust(12)}  "
                f"{row['role'].ljust(6)}  {row['team_code']}"
            )
        self.stdout.write("")

        if csv_path:
            with open(csv_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["username", "password", "role", "team_code", "team_name"]
                )
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(self.style.SUCCESS(f"Wrote {csv_path}"))

        settings_row.refresh_from_db()
        active = EntryQuestion.objects.filter(is_active=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Game status: {settings_row.status}. "
                f"{active} active entry questions, sheet of {settings_row.entry_question_count}, "
                f"{settings_row.entry_required_correct} correct needed "
                f"(grace {settings_row.entry_grace_minutes} min, "
                f"{settings_row.entry_max_retries} retries). "
                f"Every team funded to {settings_row.initial_balance}."
            )
        )
        if not Node.objects.filter(level_id="spawn").exists():
            self.stdout.write(
                self.style.WARNING(
                    "No spawn nodes found — run `uv run manage.py import_graph` "
                    "before teams try to claim a start node."
                )
            )
