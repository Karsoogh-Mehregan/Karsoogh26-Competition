from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0029_node_board"),
    ]

    operations = [
        migrations.AddField(
            model_name="gamesettings",
            name="leaderboard_frozen",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When on, competing teams see a snapshot of the rankings taken "
                    "at the freeze; organisers keep seeing live numbers."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamesettings",
            name="leaderboard_snapshot",
            field=models.JSONField(
                blank=True,
                help_text="Per-board rankings captured when the freeze is turned on.",
                null=True,
            ),
        ),
    ]
