from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("game", "0032_seed_economy_costs")]

    operations = [
        migrations.AddField(
            model_name="gamesettings",
            name="max_open_attempts",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text=(
                    "How many reserved-but-unanswered questions a team may hold at once. "
                    "A question the team has answered no longer counts, graded or not; "
                    "0 turns the cap off."
                ),
            ),
        ),
    ]
