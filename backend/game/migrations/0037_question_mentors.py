"""Question.mentor (FK) becomes Question.mentors (M2M).

The FK rows are copied into the join table before the column is dropped, so an
existing assignment survives the widening; a question with no mentor stays
unassigned and off every queue, exactly as before.
"""

from django.conf import settings
from django.db import migrations, models


def copy_mentor_to_mentors(apps, schema_editor):
    Question = apps.get_model("game", "Question")
    for question in Question.objects.exclude(mentor__isnull=True).iterator():
        question.mentors.add(question.mentor_id)


def copy_mentors_to_mentor(apps, schema_editor):
    Question = apps.get_model("game", "Question")
    for question in Question.objects.prefetch_related("mentors").iterator():
        first = question.mentors.first()
        if first is not None:
            question.mentor_id = first.pk
            question.save(update_fields=["mentor"])


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0036_alter_question_mentor"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="mentors",
            field=models.ManyToManyField(
                blank=True,
                help_text="The mentors who grade submissions for this question. Empty = every mentor queue.",
                related_name="grading_questions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(copy_mentor_to_mentors, copy_mentors_to_mentor),
        migrations.RemoveIndex(model_name="question", name="question_mentor_idx"),
        migrations.RemoveField(model_name="question", name="mentor"),
    ]
