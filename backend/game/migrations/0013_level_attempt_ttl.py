from django.db import migrations, models


def copy_ttl_from_game_settings(apps, schema_editor):
    GameSettings = apps.get_model("game", "GameSettings")
    LevelConfig = apps.get_model("game", "LevelConfig")
    row = GameSettings.objects.filter(pk=1).first()
    minutes = getattr(row, "attempt_ttl_minutes", None) if row is not None else None
    if minutes:
        LevelConfig.objects.all().update(attempt_ttl_minutes=minutes)


def uncopy_ttl(apps, schema_editor):
    GameSettings = apps.get_model("game", "GameSettings")
    LevelConfig = apps.get_model("game", "LevelConfig")
    row = GameSettings.objects.filter(pk=1).first()
    if row is None:
        return
    first = LevelConfig.objects.order_by("level").first()
    if first is not None:
        row.attempt_ttl_minutes = first.attempt_ttl_minutes
        row.save(update_fields=["attempt_ttl_minutes"])


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0012_starting_balance_400"),
    ]

    operations = [
        migrations.AddField(
            model_name="levelconfig",
            name="attempt_ttl_minutes",
            field=models.PositiveSmallIntegerField(
                default=15,
                help_text="Minutes the team has to answer after a question is assigned on this level.",
            ),
        ),
        migrations.AddConstraint(
            model_name="levelconfig",
            constraint=models.CheckConstraint(
                condition=models.Q(("attempt_ttl_minutes__gte", 1)),
                name="levelconfig_attempt_ttl_positive",
            ),
        ),
        migrations.RunPython(copy_ttl_from_game_settings, uncopy_ttl),
        migrations.RemoveField(
            model_name="gamesettings",
            name="attempt_ttl_minutes",
        ),
    ]
