import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0007_matchmaking_dismissal_and_territory_knockout")]

    operations = [
        migrations.CreateModel(
            name="OlympicsPlayerRun",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("round_number", models.PositiveIntegerField()),
                ("attempts", models.JSONField(blank=True, default=list)),
                (
                    "best_distance",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True),
                ),
                ("completed_at", models.DateTimeField(auto_now=True)),
                (
                    "match",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="player_runs",
                        to="events.olympicsmatch",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="olympics_player_runs",
                        to="teams.team",
                    ),
                ),
            ],
            options={"ordering": ["round_number", "team_id"]},
        ),
        migrations.AddConstraint(
            model_name="olympicsplayerrun",
            constraint=models.UniqueConstraint(
                fields=("match", "team", "round_number"), name="olympics_one_player_run_per_round"
            ),
        ),
        migrations.AddConstraint(
            model_name="olympicsplayerrun",
            constraint=models.CheckConstraint(
                condition=models.Q(("round_number__gte", 1)),
                name="olympics_player_run_round_positive",
            ),
        ),
    ]
