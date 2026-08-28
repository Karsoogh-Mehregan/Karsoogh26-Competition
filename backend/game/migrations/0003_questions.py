# Generated manually for Question / Submission feature

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import game.validators


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0002_seed_economy"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Question",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.SlugField(max_length=32, unique=True)),
                ("title", models.CharField(max_length=200)),
                ("body", models.TextField(help_text="Markdown")),
                (
                    "attachment",
                    models.FileField(
                        blank=True,
                        upload_to="questions/",
                        validators=[
                            game.validators.validate_upload_extension,
                            game.validators.validate_upload_size,
                        ],
                    ),
                ),
                (
                    "answer_type",
                    models.CharField(
                        choices=[
                            ("text", "متن"),
                            ("file", "فایل"),
                            ("numeric", "عددی"),
                        ],
                        max_length=8,
                    ),
                ),
                (
                    "answer_key",
                    models.TextField(
                        blank=True,
                        help_text="Mentor reference only — never exposed to teams.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "level",
                    models.ForeignKey(
                        db_column="level",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="questions",
                        to="game.levelconfig",
                    ),
                ),
            ],
            options={
                "ordering": ["level", "code"],
            },
        ),
        migrations.AddField(
            model_name="occupancy",
            name="question",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="occupancies",
                to="game.question",
            ),
        ),
        migrations.CreateModel(
            name="TeamQuestion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                (
                    "occupancy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="question_assignments",
                        to="game.occupancy",
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="team_assignments",
                        to="game.question",
                    ),
                ),
                (
                    "team",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="served_questions",
                        to="teams.team",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Submission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("body", models.TextField(blank=True)),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        upload_to="submissions/%Y/%m/",
                        validators=[
                            game.validators.validate_upload_extension,
                            game.validators.validate_upload_size,
                        ],
                    ),
                ),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                (
                    "occupancy",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="submission",
                        to="game.occupancy",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="question",
            index=models.Index(fields=["level", "is_active"], name="question_level_active_idx"),
        ),
        migrations.AddConstraint(
            model_name="teamquestion",
            constraint=models.UniqueConstraint(
                fields=("team", "question"),
                name="teamquestion_no_repeat",
            ),
        ),
        migrations.AddIndex(
            model_name="teamquestion",
            index=models.Index(fields=["team", "question"], name="teamquestion_team_q_idx"),
        ),
        migrations.AddConstraint(
            model_name="submission",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("body", ""),
                    ("file", ""),
                    _negated=True,
                ),
                name="submission_has_content",
            ),
        ),
    ]
