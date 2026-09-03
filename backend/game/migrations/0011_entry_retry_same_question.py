"""Entry retries take another run at the same question instead of swapping it.

`replaced_at` becomes `superseded_at` via RenameField, not add-then-drop, so
rows already marked keep their marker — dropping the column first would leave
two live attempts on one position and trip `entryattempt_one_per_position`.

`entryattempt_no_repeat` narrows to current rows: a team now stacks several
tries at the same question, but only one of them is ever live.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0010_entry_question_refresh"),
        ("teams", "0002_team_color"),
    ]

    operations = [
        # Constraints reference the column, so they come off before the rename.
        migrations.RemoveConstraint(
            model_name="entryattempt",
            name="entryattempt_no_repeat",
        ),
        migrations.RemoveConstraint(
            model_name="entryattempt",
            name="entryattempt_one_per_position",
        ),
        migrations.RemoveConstraint(
            model_name="entryattempt",
            name="entryattempt_only_wrong_is_replaced",
        ),
        migrations.RenameField(
            model_name="entryattempt",
            old_name="replaced_at",
            new_name="superseded_at",
        ),
        migrations.AlterField(
            model_name="entryattempt",
            name="superseded_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Set when the team spent a retry and started a fresh try at this question."
                ),
                null=True,
            ),
        ),
        migrations.RenameField(
            model_name="gamesettings",
            old_name="entry_max_refreshes",
            new_name="entry_max_retries",
        ),
        migrations.AlterField(
            model_name="gamesettings",
            name="entry_max_retries",
            field=models.PositiveSmallIntegerField(
                default=3,
                help_text=(
                    "Extra attempts a team may take on wrongly-answered entry questions, "
                    "across the whole sheet. Raise it to be more forgiving; 0 makes every "
                    "answer final."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="gamesettings",
            name="initial_balance",
            field=models.PositiveIntegerField(
                default=400,
                help_text="Every team starts here, entry sheet cleared or not.",
            ),
        ),
        migrations.AddConstraint(
            model_name="entryattempt",
            constraint=models.UniqueConstraint(
                condition=models.Q(("superseded_at__isnull", True)),
                fields=("team", "question"),
                name="entryattempt_no_repeat",
            ),
        ),
        migrations.AddConstraint(
            model_name="entryattempt",
            constraint=models.UniqueConstraint(
                condition=models.Q(("superseded_at__isnull", True)),
                fields=("team", "position"),
                name="entryattempt_one_per_position",
            ),
        ),
        migrations.AddConstraint(
            model_name="entryattempt",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("superseded_at__isnull", True), ("is_correct", False), _connector="OR"
                ),
                name="entryattempt_only_wrong_is_superseded",
            ),
        ),
    ]
