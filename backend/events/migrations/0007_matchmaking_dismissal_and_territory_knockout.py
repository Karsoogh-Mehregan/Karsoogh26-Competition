from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0006_eventconfiguration_matchmakingticket")]

    operations = [
        migrations.AddField(
            model_name="matchmakingticket",
            name="dismissed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name="territorygame",
            name="territory_status_consistent",
        ),
        migrations.AddConstraint(
            model_name="territorygame",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        status="running",
                        active_player__isnull=False,
                        turns_completed__lt=20,
                        winner__isnull=True,
                    )
                    | models.Q(
                        status="finished",
                        active_player__isnull=True,
                        turns_completed__lte=20,
                    )
                ),
                name="territory_status_consistent",
            ),
        ),
    ]
