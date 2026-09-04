"""Put the four organiser-run event instances on a board.

An auction, a charity bag, a prize wheel and a pig event are created by an
organiser and are not attached to one team, so they store their board rather
than deriving it. Everything else in this app hangs off a team — a ticket, a
pair, a spin, a match — and reads `team.board` instead.

Existing rows go to `boys`, matching `teams.0010_team_board`; see that migration
for why the backfills must agree. The charity bag's unique start time becomes
unique per board, so both contests can run a bag in the same window.
"""

from django.db import migrations, models
from django.db.models import CheckConstraint, Q, UniqueConstraint

BACKFILL_BOARD = "boys"
_MODELS = ("auctionevent", "charitybagevent", "wheelevent", "pigevent")

_CHOICES = [("girls", "دختران"), ("boys", "پسران")]


def set_board(apps, schema_editor):
    for name in _MODELS:
        model = apps.get_model("events", name)
        model.objects.filter(board__isnull=True).update(board=BACKFILL_BOARD)
        model.objects.filter(board="").update(board=BACKFILL_BOARD)


class Migration(migrations.Migration):
    dependencies = [("events", "0009_centipede_shared_pot")]

    operations = [
        *[
            migrations.AddField(
                model_name=name,
                name="board",
                field=models.CharField(max_length=8, null=True, choices=_CHOICES),
            )
            for name in _MODELS
        ],
        migrations.RunPython(set_board, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=name,
                name="board",
                field=models.CharField(max_length=8, choices=_CHOICES),
            )
            for name in _MODELS
        ],
        migrations.RemoveConstraint(
            model_name="charitybagevent", name="charity_bag_unique_start"
        ),
        migrations.AddConstraint(
            model_name="charitybagevent",
            constraint=UniqueConstraint(
                fields=("board", "starts_at"), name="charity_bag_unique_start"
            ),
        ),
        *[
            migrations.AddConstraint(
                model_name=name,
                constraint=CheckConstraint(
                    condition=Q(board__in=["girls", "boys"]), name=f"{prefix}_board_valid"
                ),
            )
            for name, prefix in (
                ("auctionevent", "auction"),
                ("charitybagevent", "charity_bag"),
                ("pigevent", "pig"),
                ("wheelevent", "wheel"),
            )
        ],
    ]
