from django.db import models
from django.db.models import CheckConstraint, F, Q, UniqueConstraint

BOARD_SIZE = 5
TOTAL_TURNS = 20


class TerritoryGameStatus(models.TextChoices):
    RUNNING = "running", "در حال اجرا"
    FINISHED = "finished", "تمام شده"


class TerritoryAction(models.TextChoices):
    STARTING_POSITION = "starting_position", "انتخاب خانه شروع"
    NEUTRAL_CAPTURE = "neutral_capture", "تصرف خانه خنثی"
    OPPONENT_ATTACK = "opponent_attack", "حمله به حریف"


class TerritoryGame(models.Model):
    player_one = models.ForeignKey(
        "teams.Team", on_delete=models.PROTECT, related_name="territory_games_as_player_one"
    )
    player_two = models.ForeignKey(
        "teams.Team", on_delete=models.PROTECT, related_name="territory_games_as_player_two"
    )
    active_player = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="active_territory_games",
    )
    winner = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="won_territory_games",
    )
    player_one_score = models.IntegerField(default=0)
    player_two_score = models.IntegerField(default=0)
    player_one_started = models.BooleanField(default=False)
    player_two_started = models.BooleanField(default=False)
    turns_completed = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=8,
        choices=TerritoryGameStatus.choices,
        default=TerritoryGameStatus.RUNNING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(
                condition=~Q(player_one=F("player_two")),
                name="territory_two_distinct_players",
            ),
            CheckConstraint(
                condition=Q(turns_completed__gte=0, turns_completed__lte=TOTAL_TURNS),
                name="territory_turn_count_range",
            ),
            CheckConstraint(
                condition=(
                    Q(active_player=F("player_one"))
                    | Q(active_player=F("player_two"))
                    | Q(active_player__isnull=True)
                ),
                name="territory_active_is_player",
            ),
            CheckConstraint(
                condition=(
                    Q(winner=F("player_one")) | Q(winner=F("player_two")) | Q(winner__isnull=True)
                ),
                name="territory_winner_is_player",
            ),
            CheckConstraint(
                condition=(
                    Q(
                        status=TerritoryGameStatus.RUNNING,
                        active_player__isnull=False,
                        turns_completed__lt=TOTAL_TURNS,
                        winner__isnull=True,
                    )
                    | Q(
                        status=TerritoryGameStatus.FINISHED,
                        active_player__isnull=True,
                        turns_completed=TOTAL_TURNS,
                    )
                ),
                name="territory_status_consistent",
            ),
        ]

    def __str__(self):
        return f"{self.player_one} vs {self.player_two} ({self.pk})"

    @property
    def turns_remaining(self) -> int:
        return TOTAL_TURNS - self.turns_completed

    def score_for(self, team_id: int) -> int:
        if team_id == self.player_one_id:
            return self.player_one_score
        if team_id == self.player_two_id:
            return self.player_two_score
        raise ValueError("Team is not a player in this game.")

    def has_started(self, team_id: int) -> bool:
        if team_id == self.player_one_id:
            return self.player_one_started
        if team_id == self.player_two_id:
            return self.player_two_started
        raise ValueError("Team is not a player in this game.")


class TerritoryCell(models.Model):
    game = models.ForeignKey(TerritoryGame, on_delete=models.CASCADE, related_name="cells")
    row = models.PositiveSmallIntegerField()
    column = models.PositiveSmallIntegerField()
    value = models.PositiveSmallIntegerField()
    owner = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="territory_cells",
    )

    class Meta:
        ordering = ["row", "column"]
        constraints = [
            UniqueConstraint(fields=["game", "row", "column"], name="territory_cell_unique"),
            CheckConstraint(
                condition=Q(row__gte=0, row__lt=BOARD_SIZE), name="territory_cell_row_range"
            ),
            CheckConstraint(
                condition=Q(column__gte=0, column__lt=BOARD_SIZE),
                name="territory_cell_column_range",
            ),
            CheckConstraint(
                condition=Q(value__gte=1, value__lte=5), name="territory_cell_value_range"
            ),
        ]

    def __str__(self):
        return f"Game {self.game_id} [{self.row}, {self.column}] = {self.value}"


class TerritoryTurn(models.Model):
    game = models.ForeignKey(TerritoryGame, on_delete=models.CASCADE, related_name="turns")
    number = models.PositiveSmallIntegerField()
    acting_player = models.ForeignKey(
        "teams.Team", on_delete=models.PROTECT, related_name="territory_turns"
    )
    target_row = models.PositiveSmallIntegerField()
    target_column = models.PositiveSmallIntegerField()
    target_value = models.PositiveSmallIntegerField()
    action_type = models.CharField(max_length=20, choices=TerritoryAction.choices)
    dice_result = models.PositiveSmallIntegerField(null=True, blank=True)
    success = models.BooleanField()
    attacker_score_change = models.IntegerField(default=0)
    defender_score_change = models.IntegerField(default=0)
    previous_owner = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="territory_turns_lost",
    )
    new_owner = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="territory_turns_gained",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            UniqueConstraint(fields=["game", "number"], name="territory_turn_unique"),
            CheckConstraint(
                condition=Q(number__gte=1, number__lte=TOTAL_TURNS),
                name="territory_turn_number_range",
            ),
            CheckConstraint(
                condition=Q(target_row__gte=0, target_row__lt=BOARD_SIZE),
                name="territory_turn_row_range",
            ),
            CheckConstraint(
                condition=Q(target_column__gte=0, target_column__lt=BOARD_SIZE),
                name="territory_turn_column_range",
            ),
            CheckConstraint(
                condition=Q(target_value__gte=1, target_value__lte=5),
                name="territory_turn_value_range",
            ),
            CheckConstraint(
                condition=(
                    Q(action_type=TerritoryAction.STARTING_POSITION, dice_result__isnull=True)
                    | (
                        ~Q(action_type=TerritoryAction.STARTING_POSITION)
                        & Q(
                            dice_result__isnull=False,
                            dice_result__gte=1,
                            dice_result__lte=6,
                        )
                    )
                ),
                name="territory_turn_dice_consistent",
            ),
        ]

    def __str__(self):
        return f"Game {self.game_id}, turn {self.number}"
