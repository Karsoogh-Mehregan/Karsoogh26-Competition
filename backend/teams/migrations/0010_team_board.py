"""Put every team on a board: the girls' contest or the boys'.

The backfill has no correct value to read — nothing recorded which contest a
team belonged to, because until now there was only one. Every existing row is
therefore put on `boys`, and the same choice is made in
`game.migrations.0029_node_board` and `events.migrations.0010_event_board`.
Consistency across the three is what matters: a live `Occupancy` joins a team to
a node, and an `AuctionPair` joins two teams, so a split backfill would leave
rows straddling both contests.

The operator sets each team's real board in the admin before the two-board event
starts. `draft_order` and `color` become unique per board in the same step, so
both contests can run their own spawn palette and their own finishing order.
"""

from django.db import migrations, models
from django.db.models import CheckConstraint, Q, UniqueConstraint

BACKFILL_BOARD = "boys"


def set_board(apps, schema_editor):
    apps.get_model("teams", "Team").objects.filter(board="").update(board=BACKFILL_BOARD)
    apps.get_model("teams", "Team").objects.filter(board__isnull=True).update(
        board=BACKFILL_BOARD
    )


class Migration(migrations.Migration):
    dependencies = [("teams", "0009_alter_balanceevent_reason")]

    operations = [
        migrations.AddField(
            model_name="team",
            name="board",
            field=models.CharField(
                max_length=8,
                null=True,
                choices=[("girls", "دختران"), ("boys", "پسران")],
            ),
        ),
        migrations.RunPython(set_board, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="team",
            name="board",
            field=models.CharField(
                max_length=8,
                choices=[("girls", "دختران"), ("boys", "پسران")],
            ),
        ),
        migrations.RemoveConstraint(model_name="team", name="team_color_unique_when_set"),
        migrations.AlterField(
            model_name="team",
            name="draft_order",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=UniqueConstraint(
                fields=("board", "color"),
                condition=Q(color__isnull=False),
                name="team_color_unique_per_board",
            ),
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=UniqueConstraint(
                fields=("board", "draft_order"),
                condition=Q(draft_order__isnull=False),
                name="team_draft_order_unique_per_board",
            ),
        ),
        migrations.AddConstraint(
            model_name="team",
            constraint=CheckConstraint(
                condition=Q(board__in=["girls", "boys"]), name="team_board_valid"
            ),
        ),
    ]
