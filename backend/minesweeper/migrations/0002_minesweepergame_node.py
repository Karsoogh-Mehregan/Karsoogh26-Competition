"""Attach every board to the map node it is played on.

Boards created under 0001 have no node to name, so the column is added
nullable, backfilled, and only then tightened — a bare non-null `AddField`
fails on any database that already holds rows. The backfill adopts the lowest
toll node because that is where the game is reachable from; it invents an
association, but a board is history and history is not deleted to make a schema
change convenient.
"""

import django.db.models.deletion
from django.db import migrations, models


def adopt_orphan_boards(apps, schema_editor):
    Game = apps.get_model("minesweeper", "MinesweeperGame")
    Node = apps.get_model("game", "Node")

    orphans = Game.objects.filter(node__isnull=True)
    if not orphans.exists():
        return

    node = (
        Node.objects.filter(level_id="toll").order_by("code").first()
        or Node.objects.order_by("code").first()
    )
    if node is None:
        raise RuntimeError(
            "Minesweeper boards exist but the map has no nodes to attach them to. "
            "Run `manage.py import_graph` first, then migrate again."
        )
    orphans.update(node=node)


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0013_level_attempt_ttl"),
        ("minesweeper", "0001_minesweepergame"),
    ]

    operations = [
        migrations.AddField(
            model_name="minesweepergame",
            name="node",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="minesweeper_games",
                to="game.node",
            ),
        ),
        migrations.RunPython(adopt_orphan_boards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="minesweepergame",
            name="node",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="minesweeper_games",
                to="game.node",
            ),
        ),
    ]
