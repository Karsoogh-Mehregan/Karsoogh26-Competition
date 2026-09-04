import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("teams", "0002_team_color")]

    operations = [
        migrations.CreateModel(
            name="TerritoryGame",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("player_one_score", models.IntegerField(default=0)),
                ("player_two_score", models.IntegerField(default=0)),
                ("player_one_started", models.BooleanField(default=False)),
                ("player_two_started", models.BooleanField(default=False)),
                ("turns_completed", models.PositiveSmallIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[("running", "در حال اجرا"), ("finished", "تمام شده")],
                        default="running",
                        max_length=8,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "active_player",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="active_territory_games",
                        to="teams.team",
                    ),
                ),
                (
                    "player_one",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="territory_games_as_player_one",
                        to="teams.team",
                    ),
                ),
                (
                    "player_two",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="territory_games_as_player_two",
                        to="teams.team",
                    ),
                ),
                (
                    "winner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="won_territory_games",
                        to="teams.team",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="TerritoryCell",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("row", models.PositiveSmallIntegerField()),
                ("column", models.PositiveSmallIntegerField()),
                ("value", models.PositiveSmallIntegerField()),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cells",
                        to="events.territorygame",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="territory_cells",
                        to="teams.team",
                    ),
                ),
            ],
            options={"ordering": ["row", "column"]},
        ),
        migrations.CreateModel(
            name="TerritoryTurn",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("number", models.PositiveSmallIntegerField()),
                ("target_row", models.PositiveSmallIntegerField()),
                ("target_column", models.PositiveSmallIntegerField()),
                ("target_value", models.PositiveSmallIntegerField()),
                (
                    "action_type",
                    models.CharField(
                        choices=[
                            ("starting_position", "انتخاب خانه شروع"),
                            ("neutral_capture", "تصرف خانه خنثی"),
                            ("opponent_attack", "حمله به حریف"),
                        ],
                        max_length=20,
                    ),
                ),
                ("dice_result", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("success", models.BooleanField()),
                ("attacker_score_change", models.IntegerField(default=0)),
                ("defender_score_change", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "acting_player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="territory_turns",
                        to="teams.team",
                    ),
                ),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="turns",
                        to="events.territorygame",
                    ),
                ),
                (
                    "new_owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="territory_turns_gained",
                        to="teams.team",
                    ),
                ),
                (
                    "previous_owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="territory_turns_lost",
                        to="teams.team",
                    ),
                ),
            ],
            options={"ordering": ["number"]},
        ),
        migrations.AddConstraint(
            model_name="territorygame",
            constraint=models.CheckConstraint(
                condition=~models.Q(player_one=models.F("player_two")),
                name="territory_two_distinct_players",
            ),
        ),
        migrations.AddConstraint(
            model_name="territorygame",
            constraint=models.CheckConstraint(
                condition=models.Q(turns_completed__gte=0, turns_completed__lte=20),
                name="territory_turn_count_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="territorygame",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(active_player=models.F("player_one"))
                    | models.Q(active_player=models.F("player_two"))
                    | models.Q(active_player__isnull=True)
                ),
                name="territory_active_is_player",
            ),
        ),
        migrations.AddConstraint(
            model_name="territorygame",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(winner=models.F("player_one"))
                    | models.Q(winner=models.F("player_two"))
                    | models.Q(winner__isnull=True)
                ),
                name="territory_winner_is_player",
            ),
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
                        turns_completed=20,
                    )
                ),
                name="territory_status_consistent",
            ),
        ),
        migrations.AddConstraint(
            model_name="territorycell",
            constraint=models.UniqueConstraint(
                fields=("game", "row", "column"), name="territory_cell_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="territorycell",
            constraint=models.CheckConstraint(
                condition=models.Q(row__gte=0, row__lt=5),
                name="territory_cell_row_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="territorycell",
            constraint=models.CheckConstraint(
                condition=models.Q(column__gte=0, column__lt=5),
                name="territory_cell_column_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="territorycell",
            constraint=models.CheckConstraint(
                condition=models.Q(value__gte=1, value__lte=5),
                name="territory_cell_value_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="territoryturn",
            constraint=models.UniqueConstraint(
                fields=("game", "number"), name="territory_turn_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="territoryturn",
            constraint=models.CheckConstraint(
                condition=models.Q(number__gte=1, number__lte=20),
                name="territory_turn_number_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="territoryturn",
            constraint=models.CheckConstraint(
                condition=models.Q(target_row__gte=0, target_row__lt=5),
                name="territory_turn_row_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="territoryturn",
            constraint=models.CheckConstraint(
                condition=models.Q(target_column__gte=0, target_column__lt=5),
                name="territory_turn_column_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="territoryturn",
            constraint=models.CheckConstraint(
                condition=models.Q(target_value__gte=1, target_value__lte=5),
                name="territory_turn_value_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="territoryturn",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(action_type="starting_position", dice_result__isnull=True)
                    | (
                        ~models.Q(action_type="starting_position")
                        & models.Q(
                            dice_result__isnull=False,
                            dice_result__gte=1,
                            dice_result__lte=6,
                        )
                    )
                ),
                name="territory_turn_dice_consistent",
            ),
        ),
    ]
