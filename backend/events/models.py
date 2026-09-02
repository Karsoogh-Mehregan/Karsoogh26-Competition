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


class CharityBagStatus(models.TextChoices):
    SCHEDULED = "scheduled", "زمان‌بندی شده"
    ACTIVE = "active", "فعال"
    RESOLVING = "resolving", "در حال تسویه"
    FINISHED = "finished", "تمام شده"


class CharityBagAction(models.TextChoices):
    CONTRIBUTE = "contribute", "کمک به خیریه"
    REQUEST = "request", "درخواست از خیریه"


class CharityBagEvent(models.Model):
    status = models.CharField(
        max_length=10,
        choices=CharityBagStatus.choices,
        default=CharityBagStatus.SCHEDULED,
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    total_contributed = models.PositiveIntegerField(default=0)
    total_requested = models.PositiveIntegerField(default=0)
    charity_succeeded = models.BooleanField(null=True, blank=True)
    settlement_started_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-starts_at"]
        constraints = [
            CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="charity_bag_positive_window",
            ),
            UniqueConstraint(fields=["starts_at"], name="charity_bag_unique_start"),
            CheckConstraint(
                condition=(
                    Q(
                        status__in=[
                            CharityBagStatus.SCHEDULED,
                            CharityBagStatus.ACTIVE,
                            CharityBagStatus.RESOLVING,
                        ],
                        charity_succeeded__isnull=True,
                        settled_at__isnull=True,
                    )
                    | Q(
                        status=CharityBagStatus.FINISHED,
                        charity_succeeded__isnull=False,
                        settled_at__isnull=False,
                    )
                ),
                name="charity_bag_settlement_state_consistent",
            ),
        ]

    def __str__(self):
        return f"Charity Bag {self.pk} ({self.starts_at:%Y-%m-%d %H:%M})"


class CharityBagParticipation(models.Model):
    event = models.ForeignKey(
        CharityBagEvent,
        on_delete=models.CASCADE,
        related_name="participations",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.PROTECT,
        related_name="charity_bag_participations",
    )
    action = models.CharField(max_length=10, choices=CharityBagAction.choices)
    amount = models.PositiveIntegerField()
    stake_deducted = models.PositiveIntegerField()
    final_payout = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["submitted_at", "pk"]
        constraints = [
            UniqueConstraint(
                fields=["event", "team"],
                name="charity_bag_one_entry_per_team",
            ),
            CheckConstraint(condition=Q(amount__gt=0), name="charity_bag_amount_positive"),
            CheckConstraint(
                condition=Q(stake_deducted=F("amount")),
                name="charity_bag_stake_matches_amount",
            ),
        ]

    def __str__(self):
        return f"{self.team} / {self.event_id} / {self.action}"


class CentipedeStatus(models.TextChoices):
    WAITING_FOR_PLAYERS = "waiting_for_players", "در انتظار بازیکنان"
    ACTIVE = "active", "فعال"
    FINISHED = "finished", "تمام شده"


class CentipedeAction(models.TextChoices):
    TAKE = "take", "بردار"
    CONTINUE = "continue", "ادامه بده"


class CentipedeGame(models.Model):
    player_one = models.ForeignKey(
        "teams.Team",
        on_delete=models.PROTECT,
        related_name="centipede_games_as_player_one",
    )
    player_two = models.ForeignKey(
        "teams.Team",
        on_delete=models.PROTECT,
        related_name="centipede_games_as_player_two",
    )
    active_player = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="active_centipede_games",
    )
    winner = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="won_centipede_games",
    )
    round_number = models.PositiveIntegerField(default=1)
    player_one_reward = models.PositiveBigIntegerField(default=50)
    player_two_reward = models.PositiveBigIntegerField(default=200)
    actions_completed = models.PositiveIntegerField(default=0)
    player_one_final_payout = models.PositiveBigIntegerField(default=0)
    player_two_final_payout = models.PositiveBigIntegerField(default=0)
    status = models.CharField(
        max_length=19,
        choices=CentipedeStatus.choices,
        default=CentipedeStatus.ACTIVE,
    )
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(
                condition=~Q(player_one=F("player_two")),
                name="centipede_two_distinct_players",
            ),
            CheckConstraint(
                condition=Q(round_number__gte=1),
                name="centipede_round_positive",
            ),
            CheckConstraint(
                condition=Q(player_one_reward__gte=50, player_two_reward__gte=200),
                name="centipede_rewards_minimum",
            ),
            CheckConstraint(
                condition=(
                    Q(active_player=F("player_one"))
                    | Q(active_player=F("player_two"))
                    | Q(active_player__isnull=True)
                ),
                name="centipede_active_is_player",
            ),
            CheckConstraint(
                condition=(
                    Q(winner=F("player_one")) | Q(winner=F("player_two")) | Q(winner__isnull=True)
                ),
                name="centipede_winner_is_player",
            ),
            CheckConstraint(
                condition=(
                    Q(
                        status=CentipedeStatus.WAITING_FOR_PLAYERS,
                        active_player__isnull=True,
                        winner__isnull=True,
                        finished_at__isnull=True,
                        player_one_final_payout=0,
                        player_two_final_payout=0,
                    )
                    | Q(
                        status=CentipedeStatus.ACTIVE,
                        active_player__isnull=False,
                        winner__isnull=True,
                        finished_at__isnull=True,
                        player_one_final_payout=0,
                        player_two_final_payout=0,
                    )
                    | Q(
                        status=CentipedeStatus.FINISHED,
                        active_player__isnull=True,
                        winner__isnull=False,
                        finished_at__isnull=False,
                    )
                ),
                name="centipede_status_consistent",
            ),
            CheckConstraint(
                condition=(
                    Q(
                        winner=F("player_one"),
                        player_one_final_payout__gt=0,
                        player_two_final_payout=0,
                    )
                    | Q(
                        winner=F("player_two"),
                        player_one_final_payout=0,
                        player_two_final_payout__gt=0,
                    )
                    | Q(winner__isnull=True)
                ),
                name="centipede_payout_matches_winner",
            ),
        ]

    def __str__(self):
        return f"Centipede {self.player_one} vs {self.player_two} ({self.pk})"


class CentipedeDecision(models.Model):
    game = models.ForeignKey(
        CentipedeGame,
        on_delete=models.CASCADE,
        related_name="decisions",
    )
    sequence = models.PositiveIntegerField()
    round_number = models.PositiveIntegerField()
    actor = models.ForeignKey(
        "teams.Team",
        on_delete=models.PROTECT,
        related_name="centipede_decisions",
    )
    action = models.CharField(max_length=8, choices=CentipedeAction.choices)
    displayed_reward = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            UniqueConstraint(fields=["game", "sequence"], name="centipede_decision_sequence"),
            UniqueConstraint(
                fields=["game", "round_number", "actor"],
                name="centipede_one_decision_per_player_round",
            ),
            CheckConstraint(
                condition=Q(sequence__gte=1, round_number__gte=1, displayed_reward__gt=0),
                name="centipede_decision_values_positive",
            ),
        ]

    def __str__(self):
        return f"Centipede {self.game_id}, decision {self.sequence}"
