"""Per-question grading scale, plus the partial_grade release reason.

max_grade is added nullable and backfilled to 100 before it is tightened, because
the production database holds a live question bank. 100 is the defensible value:
it is the scale every grade recorded so far was entered on, so an already-graded
occupancy keeps the exact multiplier it was paid with.
"""

from django.db import migrations, models


def backfill_max_grade(apps, schema_editor):
    Question = apps.get_model("game", "Question")
    Question.objects.filter(max_grade__isnull=True).update(max_grade=100)


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0018_stronger_neighbourhood_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="max_grade",
            field=models.PositiveSmallIntegerField(null=True),
        ),
        migrations.RunPython(backfill_max_grade, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="question",
            name="max_grade",
            field=models.PositiveSmallIntegerField(
                default=100,
                help_text=(
                    "The scale the mentor grades on. "
                    "Payout is grade/max_grade of the floor reward."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name="question",
            constraint=models.CheckConstraint(
                condition=models.Q(("max_grade__gte", 1), ("max_grade__lte", 100)),
                name="question_max_grade_range",
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
                ],
                max_length=16,
            ),
        ),
    ]
