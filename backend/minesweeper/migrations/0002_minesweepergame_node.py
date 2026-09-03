import django.db.models.deletion
from django.db import migrations, models


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
                on_delete=django.db.models.deletion.PROTECT,
                related_name="minesweeper_games",
                to="game.node",
            ),
        ),
    ]
