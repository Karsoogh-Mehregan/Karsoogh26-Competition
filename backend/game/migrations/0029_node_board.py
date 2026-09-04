"""Give every node a board, so each contest gets its own copy of the map.

Node codes stay exactly as they are. Uniqueness moves from `code` alone to
(`board`, `code`), so the girls' `L1_0` and the boys' `L1_0` are two rows under
one name: the SPA keeps a single `graph_data.json` and a single colour table,
and no existing `Occupancy` is disturbed, because nothing is renamed.

Existing rows go to `boys`, matching `teams.0010_team_board` — see that
migration for why the two must agree. The second copy of the map is content, not
schema, and is created by `manage.py import_graph --board girls`.
"""

from django.db import migrations, models
from django.db.models import CheckConstraint, Q, UniqueConstraint

BACKFILL_BOARD = "boys"


def set_board(apps, schema_editor):
    Node = apps.get_model("game", "Node")
    Node.objects.filter(board__isnull=True).update(board=BACKFILL_BOARD)
    Node.objects.filter(board="").update(board=BACKFILL_BOARD)


class Migration(migrations.Migration):
    dependencies = [("game", "0028_merge_0027_design_lock_0027_merge_20260904_2202")]

    operations = [
        migrations.AddField(
            model_name="node",
            name="board",
            field=models.CharField(
                max_length=8,
                null=True,
                choices=[("girls", "دختران"), ("boys", "پسران")],
            ),
        ),
        migrations.RunPython(set_board, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="node",
            name="board",
            field=models.CharField(
                max_length=8,
                choices=[("girls", "دختران"), ("boys", "پسران")],
            ),
        ),
        migrations.AlterField(
            model_name="node",
            name="code",
            field=models.SlugField(max_length=32),
        ),
        migrations.AlterModelOptions(name="node", options={"ordering": ["board", "code"]}),
        migrations.AddConstraint(
            model_name="node",
            constraint=UniqueConstraint(fields=("board", "code"), name="node_unique_per_board"),
        ),
        migrations.AddConstraint(
            model_name="node",
            constraint=CheckConstraint(
                condition=Q(board__in=["girls", "boys"]), name="node_board_valid"
            ),
        ),
    ]
