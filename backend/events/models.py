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
                        turns_completed__lte=TOTAL_TURNS,
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
    PRODUCE = "produce", "تولید"
    SPLIT = "split", "توافق"
    STEAL = "steal", "دزدی"
    PRESERVE = "preserve", "قناعت"


class CentipedeGame(models.Model):
    rules_version = models.PositiveSmallIntegerField(default=2)
    pot = models.PositiveIntegerField(default=200)
    production_rounds = models.PositiveSmallIntegerField(default=0)
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
                        winner__isnull=True,
                        finished_at__isnull=True,
                        player_one_final_payout=0,
                        player_two_final_payout=0,
                    )
                    | Q(
                        status=CentipedeStatus.FINISHED,
                        active_player__isnull=True,
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
                    | Q(rules_version=2)
                ),
                name="centipede_payout_matches_winner",
            ),
            CheckConstraint(
                condition=Q(rules_version=1)
                | Q(
                    production_rounds__lte=4,
                    pot=200 + F("production_rounds") * 200,
                    round_number=F("production_rounds") + 1,
                    pot__gte=F("player_one_final_payout") + F("player_two_final_payout"),
                ),
                name="centipede_pool_consistent",
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


class OlympicsMiniGame(models.TextChoices):
    COIN_NEAR_WALL = "coin_near_wall", "سکه نزدیک دیوار"
    MARBLE_TARGET = "marble_target", "تیله هدف"


class OlympicsStatus(models.TextChoices):
    CREATED = "created", "ساخته شده"
    ACTIVE = "active", "در حال اجرا"
    WAITING_FOR_RESULT = "waiting_for_result", "در انتظار نتیجه"
    TIEBREAK = "tiebreak", "تساوی‌شکن"
    FINISHED = "finished", "تمام شده"


class OlympicsOutcome(models.TextChoices):
    PLAYER_ONE = "player_one", "بازیکن اول"
    PLAYER_TWO = "player_two", "بازیکن دوم"
    TIE = "tie", "تساوی"


class OlympicsMatch(models.Model):
    mini_game = models.CharField(max_length=16, choices=OlympicsMiniGame.choices)
    player_one = models.ForeignKey(
        "teams.Team",
        on_delete=models.PROTECT,
        related_name="olympics_matches_as_player_one",
    )
    player_two = models.ForeignKey(
        "teams.Team",
        on_delete=models.PROTECT,
        related_name="olympics_matches_as_player_two",
    )
    scoring_zones = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=18,
        choices=OlympicsStatus.choices,
        default=OlympicsStatus.CREATED,
    )
    winner = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="won_olympics_matches",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(
                condition=~Q(player_one=F("player_two")),
                name="olympics_two_distinct_players",
            ),
            CheckConstraint(
                condition=(
                    Q(winner=F("player_one")) | Q(winner=F("player_two")) | Q(winner__isnull=True)
                ),
                name="olympics_winner_is_player",
            ),
            CheckConstraint(
                condition=(
                    Q(
                        status=OlympicsStatus.CREATED,
                        started_at__isnull=True,
                        finished_at__isnull=True,
                        winner__isnull=True,
                    )
                    | Q(
                        status__in=[
                            OlympicsStatus.ACTIVE,
                            OlympicsStatus.WAITING_FOR_RESULT,
                            OlympicsStatus.TIEBREAK,
                        ],
                        started_at__isnull=False,
                        finished_at__isnull=True,
                        winner__isnull=True,
                    )
                    | Q(
                        status=OlympicsStatus.FINISHED,
                        started_at__isnull=False,
                        finished_at__isnull=False,
                        winner__isnull=False,
                    )
                ),
                name="olympics_status_consistent",
            ),
        ]

    def __str__(self):
        return f"Olympics {self.player_one} vs {self.player_two} ({self.pk})"


class OlympicsResult(models.Model):
    match = models.ForeignKey(
        OlympicsMatch,
        on_delete=models.CASCADE,
        related_name="results",
    )
    request_id = models.UUIDField(unique=True)
    round_number = models.PositiveIntegerField()
    player_one_attempts = models.JSONField(default=list, blank=True)
    player_two_attempts = models.JSONField(default=list, blank=True)
    player_one_total = models.PositiveIntegerField(null=True, blank=True)
    player_two_total = models.PositiveIntegerField(null=True, blank=True)
    player_one_best_distance = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True
    )
    player_two_best_distance = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True
    )
    outcome = models.CharField(max_length=10, choices=OlympicsOutcome.choices)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="recorded_olympics_results",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["round_number"]
        constraints = [
            UniqueConstraint(
                fields=["match", "round_number"],
                name="olympics_one_result_per_round",
            ),
            CheckConstraint(
                condition=Q(round_number__gte=1),
                name="olympics_result_round_positive",
            ),
            CheckConstraint(
                condition=(
                    Q(player_one_total__isnull=True, player_two_total__isnull=True)
                    | Q(player_one_total__isnull=False, player_two_total__isnull=False)
                ),
                name="olympics_totals_pair",
            ),
            CheckConstraint(
                condition=(
                    Q(
                        player_one_best_distance__isnull=True,
                        player_two_best_distance__isnull=True,
                    )
                    | Q(
                        player_one_best_distance__isnull=False,
                        player_two_best_distance__isnull=False,
                    )
                ),
                name="olympics_distances_pair",
            ),
        ]

    def __str__(self):
        return f"Olympics {self.match_id}, round {self.round_number}"


class OlympicsPlayerRun(models.Model):
    match = models.ForeignKey(OlympicsMatch, on_delete=models.CASCADE, related_name="player_runs")
    team = models.ForeignKey(
        "teams.Team", on_delete=models.PROTECT, related_name="olympics_player_runs"
    )
    round_number = models.PositiveIntegerField()
    attempts = models.JSONField(default=list, blank=True)
    best_distance = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    completed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["round_number", "team_id"]
        constraints = [
            UniqueConstraint(
                fields=["match", "team", "round_number"],
                name="olympics_one_player_run_per_round",
            ),
            CheckConstraint(
                condition=Q(round_number__gte=1), name="olympics_player_run_round_positive"
            ),
        ]


class AuctionStatus(models.TextChoices):
    SCHEDULED = "scheduled", "زمان‌بندی‌شده"
    ACTIVE = "active", "فعال"
    FINISHED = "finished", "تمام‌شده"
    CANCELLED = "cancelled", "لغوشده"


class AuctionEvent(models.Model):
    status = models.CharField(
        max_length=10, choices=AuctionStatus.choices, default=AuctionStatus.SCHEDULED
    )
    reward = models.PositiveIntegerField(default=1000)
    opening_bid = models.PositiveIntegerField(default=10)
    duration_seconds = models.PositiveIntegerField(default=600)
    ranking_snapshot = models.JSONField(default=list)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    settled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(condition=Q(reward__gt=0), name="auction_reward_positive"),
            CheckConstraint(condition=Q(opening_bid__gt=0), name="auction_opening_positive"),
            CheckConstraint(condition=Q(duration_seconds__gt=0), name="auction_duration_positive"),
            CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="auction_window_positive"
            ),
        ]


class AuctionPair(models.Model):
    event = models.ForeignKey(AuctionEvent, on_delete=models.CASCADE, related_name="pairs")
    team_one = models.ForeignKey(
        "teams.Team", on_delete=models.PROTECT, related_name="auctions_as_team_one"
    )
    team_two = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="auctions_as_team_two",
    )
    rank_one = models.PositiveIntegerField()
    rank_two = models.PositiveIntegerField(null=True, blank=True)
    team_one_bid = models.PositiveIntegerField(default=0)
    team_two_bid = models.PositiveIntegerField(default=0)
    highest_bid = models.PositiveIntegerField(default=0)
    highest_bidder = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="leading_auctions",
    )
    winner = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="won_auctions",
    )
    status = models.CharField(max_length=10, choices=AuctionStatus.choices)
    automatic_award = models.BooleanField(default=False)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["rank_one"]
        constraints = [
            CheckConstraint(
                condition=Q(team_two__isnull=True) | ~Q(team_one=F("team_two")),
                name="auction_pair_distinct_teams",
            ),
            UniqueConstraint(fields=["event", "team_one"], name="auction_unique_team_one"),
            UniqueConstraint(fields=["event", "team_two"], name="auction_unique_team_two"),
        ]


class AuctionBid(models.Model):
    pair = models.ForeignKey(AuctionPair, on_delete=models.CASCADE, related_name="bids")
    request_id = models.UUIDField(unique=True)
    sequence = models.PositiveIntegerField()
    team = models.ForeignKey("teams.Team", on_delete=models.PROTECT, related_name="auction_bids")
    amount = models.PositiveIntegerField()
    committed_delta = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            UniqueConstraint(fields=["pair", "sequence"], name="auction_bid_sequence"),
            CheckConstraint(condition=Q(amount__gt=0), name="auction_bid_amount_positive"),
            CheckConstraint(condition=Q(committed_delta__gt=0), name="auction_bid_delta_positive"),
        ]


class WheelStatus(models.TextChoices):
    SCHEDULED = "scheduled", "زمان‌بندی‌شده"
    ACTIVE = "active", "فعال"
    GRAND_PRIZE_CLAIMED = "grand_prize_claimed", "جایزه بزرگ برنده شد"
    FINISHED = "finished", "تمام‌شده"
    CANCELLED = "cancelled", "لغوشده"


class WheelPrizeType(models.TextChoices):
    GLORIUM = "glorium", "گلوریوم"
    MERCHANDISE = "merchandise", "کالا"
    GRAND_PRIZE = "grand_prize", "جایزه بزرگ"


class WheelDeliveryStatus(models.TextChoices):
    NOT_APPLICABLE = "not_applicable", "نامرتبط"
    PENDING = "pending", "در انتظار تحویل"
    DELIVERED = "delivered", "تحویل‌شده"


class WheelEvent(models.Model):
    status = models.CharField(
        max_length=19, choices=WheelStatus.choices, default=WheelStatus.SCHEDULED
    )
    spin_cost = models.PositiveIntegerField(default=10)
    total_collected = models.PositiveIntegerField(default=0)
    grand_prize_winner = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wheel_grand_prizes",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [CheckConstraint(condition=Q(spin_cost__gt=0), name="wheel_cost_positive")]


class WheelPrize(models.Model):
    event = models.ForeignKey(WheelEvent, on_delete=models.CASCADE, related_name="prizes")
    code = models.SlugField(max_length=32)
    prize_type = models.CharField(max_length=11, choices=WheelPrizeType.choices)
    display_name = models.CharField(max_length=100)
    glorium_amount = models.PositiveIntegerField(default=0)
    reward_data = models.JSONField(default=dict, blank=True)
    weight = models.PositiveIntegerField()
    available = models.BooleanField(default=True)
    stock = models.PositiveIntegerField(null=True, blank=True)
    claimed = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            UniqueConstraint(fields=["event", "code"], name="wheel_prize_code"),
            CheckConstraint(condition=Q(weight__gt=0), name="wheel_prize_weight_positive"),
        ]


class WheelSpin(models.Model):
    event = models.ForeignKey(WheelEvent, on_delete=models.CASCADE, related_name="spins")
    request_id = models.UUIDField(unique=True)
    team = models.ForeignKey("teams.Team", on_delete=models.PROTECT, related_name="wheel_spins")
    spin_cost = models.PositiveIntegerField()
    prize = models.ForeignKey(WheelPrize, on_delete=models.PROTECT, related_name="spins")
    prize_type = models.CharField(max_length=11, choices=WheelPrizeType.choices)
    prize_name = models.CharField(max_length=100)
    glorium_payout = models.PositiveIntegerField(default=0)
    delivery_status = models.CharField(
        max_length=14,
        choices=WheelDeliveryStatus.choices,
        default=WheelDeliveryStatus.NOT_APPLICABLE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class PigEventStatus(models.TextChoices):
    ACTIVE = "active", "فعال"
    FINISHED = "finished", "تمام‌شده"


class PigGameStatus(models.TextChoices):
    ACTIVE = "active", "فعال"
    FINISHED_CASHED_OUT = "finished_cashed_out", "برداشت‌شده"
    FINISHED_ROLLED_ONE = "finished_rolled_one", "باخت با تاس یک"
    FINISHED_MAX_POT = "finished_max_pot", "رسیدن به سقف"


class PigEvent(models.Model):
    status = models.CharField(
        max_length=8, choices=PigEventStatus.choices, default=PigEventStatus.ACTIVE
    )
    entry_fee = models.PositiveIntegerField(default=200)
    max_pot = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(condition=Q(entry_fee__gt=0), name="pig_entry_fee_positive"),
            CheckConstraint(condition=Q(max_pot__gt=0), name="pig_max_pot_positive"),
        ]


class PigGame(models.Model):
    event = models.ForeignKey(PigEvent, on_delete=models.PROTECT, related_name="games")
    team = models.ForeignKey("teams.Team", on_delete=models.PROTECT, related_name="pig_games")
    entry_fee = models.PositiveIntegerField()
    max_pot = models.PositiveIntegerField()
    pot = models.PositiveIntegerField(default=0)
    rolls_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=PigGameStatus.choices, default=PigGameStatus.ACTIVE
    )
    final_payout = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            UniqueConstraint(
                fields=["event", "team"],
                condition=Q(status=PigGameStatus.ACTIVE),
                name="pig_one_active_game_per_team",
            ),
            CheckConstraint(condition=Q(pot__lte=F("max_pot")), name="pig_pot_below_max"),
        ]


class PigRoll(models.Model):
    game = models.ForeignKey(PigGame, on_delete=models.CASCADE, related_name="rolls")
    request_id = models.UUIDField(unique=True)
    number = models.PositiveIntegerField()
    dice_result = models.PositiveSmallIntegerField()
    amount_added = models.PositiveIntegerField(default=0)
    pot_after = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            UniqueConstraint(fields=["game", "number"], name="pig_roll_number"),
            CheckConstraint(
                condition=Q(dice_result__gte=1, dice_result__lte=6), name="pig_die_range"
            ),
        ]


class PigActionReceipt(models.Model):
    game = models.ForeignKey(PigGame, on_delete=models.CASCADE, related_name="action_receipts")
    request_id = models.UUIDField(unique=True)
    action = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)


class EventCode(models.TextChoices):
    TERRITORY_CONTROL = "territory_control", "نبرد قلمرو"
    CHARITY_BAG = "charity_bag", "کیسه خیریه"
    CENTIPEDE = "centipede", "بازی هزارپا"
    OLYMPICS_COIN = "olympics_coin", "سکه نزدیک دیوار"
    OLYMPICS_MARBLE = "olympics_marble", "تیله هدف"
    LIMITED_AUCTION = "limited_auction", "حراج محدود"
    PRIZE_WHEEL = "prize_wheel", "گردونه شانس"
    PIG = "pig", "بازی خوک"


class EventConfiguration(models.Model):
    code = models.CharField(max_length=32, choices=EventCode.choices, unique=True)
    enabled = models.BooleanField(default=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            CheckConstraint(
                condition=Q(duration_seconds__isnull=True) | Q(duration_seconds__gt=0),
                name="event_configuration_duration_positive",
            )
        ]

    def __str__(self):
        return self.get_code_display()


class MatchmakingStatus(models.TextChoices):
    WAITING = "waiting", "در انتظار"
    MATCHED = "matched", "جفت‌شده"
    CANCELLED = "cancelled", "لغوشده"


class MatchmakingTicket(models.Model):
    event_code = models.CharField(max_length=32, choices=EventCode.choices)
    team = models.ForeignKey(
        "teams.Team", on_delete=models.PROTECT, related_name="matchmaking_tickets"
    )
    status = models.CharField(
        max_length=10, choices=MatchmakingStatus.choices, default=MatchmakingStatus.WAITING
    )
    matched_team = models.ForeignKey(
        "teams.Team",
        on_delete=models.PROTECT,
        related_name="matched_against_tickets",
        null=True,
        blank=True,
    )
    match_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    matched_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            UniqueConstraint(
                fields=["event_code", "team"],
                condition=Q(status=MatchmakingStatus.WAITING),
                name="one_waiting_ticket_per_team_event",
            ),
            CheckConstraint(
                condition=~Q(team=F("matched_team")), name="matchmaking_distinct_teams"
            ),
        ]
