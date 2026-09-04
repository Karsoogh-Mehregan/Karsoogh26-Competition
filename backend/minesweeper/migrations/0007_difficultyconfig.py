"""Turn the three hard-coded difficulties into editable `DifficultyConfig` rows.

Board size, mine count and base score used to be constants in `models.py`, which
meant retuning a difficulty was a deploy. They become rows here, seeded with
exactly the numbers that were compiled in, so an existing database keeps playing
the boards it already had.

Order matters: the rows are seeded *before* the char columns become foreign keys,
because the FK constraint is validated against the rows already stored. The old
`minesweepergame_layout_matches_difficulty` check has to go for the same reason
the config exists at all — once a difficulty is editable, a stored board is a
snapshot of what it was, not a restatement of what the config says today. Every
existing board keeps its own width/height/mine_count and gains `base_score`
backfilled from its difficulty, so retuning cannot rescore a board in flight.
"""

import django.db.models.deletion
from django.db import migrations, models

# The values that were constants in models.py before this migration.
# `seed` is called by name from conftest, not only by the migration runner: a
# transactional test truncates these rows and has to put them back. Keep the
# name, and keep it re-runnable.
SEED = [
    ("easy", "آسان", 9, 9, 10, 100, 10),
    ("medium", "متوسط", 16, 16, 40, 250, 20),
    ("hard", "سخت", 30, 16, 99, 500, 30),
]


def seed(apps, schema_editor):
    DifficultyConfig = apps.get_model("minesweeper", "DifficultyConfig")
    for key, label, width, height, mine_count, base_score, sort_order in SEED:
        DifficultyConfig.objects.get_or_create(
            key=key,
            defaults={
                "label": label,
                "width": width,
                "height": height,
                "mine_count": mine_count,
                "base_score": base_score,
                "sort_order": sort_order,
            },
        )


def unseed(apps, schema_editor):
    """Drop only the shipped rows; a difficulty an organiser added is theirs."""
    DifficultyConfig = apps.get_model("minesweeper", "DifficultyConfig")
    DifficultyConfig.objects.filter(key__in=[row[0] for row in SEED]).delete()


def backfill_base_score(apps, schema_editor):
    """Give every stored board the base score its difficulty had at build time."""
    Game = apps.get_model("minesweeper", "MinesweeperGame")
    for key, _label, _w, _h, _mines, base_score, _order in SEED:
        Game.objects.filter(difficulty=key).update(base_score=base_score)


class Migration(migrations.Migration):
    dependencies = [("minesweeper", "0006_minesweepersettings_and_more")]

    operations = [
        migrations.CreateModel(
            name="DifficultyConfig",
            fields=[
                ("key", models.SlugField(max_length=16, primary_key=True, serialize=False)),
                ("label", models.CharField(help_text="Shown to players, in Persian.", max_length=32)),
                ("width", models.PositiveSmallIntegerField()),
                ("height", models.PositiveSmallIntegerField()),
                ("mine_count", models.PositiveSmallIntegerField()),
                (
                    "base_score",
                    models.PositiveIntegerField(
                        help_text="Win pays this plus the same again minus the seconds taken."
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(
                        default=0,
                        help_text="Order in admin and in any difficulty picker; low first.",
                    ),
                ),
            ],
            options={
                "verbose_name": "difficulty config",
                "verbose_name_plural": "difficulty configs",
                "ordering": ["sort_order", "key"],
            },
        ),
        migrations.AddConstraint(
            model_name="difficultyconfig",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("height__gte", 2),
                    ("height__lte", 40),
                    ("width__gte", 2),
                    ("width__lte", 40),
                ),
                name="difficultyconfig_dimension_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="difficultyconfig",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("mine_count__gte", 1),
                    (
                        "mine_count__lt",
                        models.F("width") * models.F("height"),
                    ),
                ),
                name="difficultyconfig_mine_count_range",
            ),
        ),
        migrations.RunPython(seed, unseed),
        migrations.RemoveConstraint(
            model_name="minesweepergame",
            name="minesweepergame_layout_matches_difficulty",
        ),
        migrations.AddField(
            model_name="minesweepergame",
            name="base_score",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Snapshot of the difficulty's base score, so retuning cannot "
                    "rescore a live board."
                ),
            ),
        ),
        migrations.RunPython(backfill_base_score, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="minesweepergame",
            name="difficulty",
            field=models.ForeignKey(
                db_column="difficulty",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="games",
                to="minesweeper.difficultyconfig",
            ),
        ),
        migrations.AlterField(
            model_name="minesweepersettings",
            name="difficulty",
            field=models.ForeignKey(
                db_column="difficulty",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="node_settings",
                to="minesweeper.difficultyconfig",
            ),
        ),
    ]
