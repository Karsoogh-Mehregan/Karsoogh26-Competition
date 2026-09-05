from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0034_acquisition_source_buyout"),
    ]

    operations = [
        migrations.AddField(
            model_name="node",
            name="gelled",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Locked by the gel item: nobody may enter until the game is restarted."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="occupancy",
            name="release_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("zero_grade", "نمره صفر"),
                    ("partial_grade", "نمره ناقص"),
                    ("expired", "منقضی شد"),
                    ("duel_lost", "باخت دوئل"),
                    ("bought_out", "خریداری شد"),
                    ("item_takeover", "آیتم"),
                    ("gelled", "گِل"),
                ],
                max_length=16,
            ),
        ),
    ]
