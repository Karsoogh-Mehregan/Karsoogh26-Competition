from django.utils import timezone
from rest_framework import serializers

from core.openapi import extend_schema_field
from teams.models import Team

from .models import (
    BOARD_SIZE,
    AuctionBid,
    AuctionEvent,
    AuctionPair,
    CentipedeDecision,
    CentipedeGame,
    CharityBagEvent,
    CharityBagParticipation,
    CharityBagStatus,
    OlympicsMatch,
    OlympicsMiniGame,
    OlympicsResult,
    PigEvent,
    PigGame,
    PigRoll,
    TerritoryCell,
    TerritoryGame,
    TerritoryGameStatus,
    TerritoryTurn,
    WheelEvent,
    WheelPrizeType,
    WheelSpin,
)


class TeamIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ("code", "name", "color")
        read_only_fields = fields


class TerritoryCellSerializer(serializers.ModelSerializer):
    owner = TeamIdentitySerializer(read_only=True, allow_null=True)

    class Meta:
        model = TerritoryCell
        fields = ("row", "column", "value", "owner")
        read_only_fields = fields


class TerritoryTargetSerializer(serializers.Serializer):
    row = serializers.IntegerField(read_only=True)
    column = serializers.IntegerField(read_only=True)


class TerritoryOwnershipChangeSerializer(serializers.Serializer):
    previous_owner = TeamIdentitySerializer(read_only=True, allow_null=True)
    new_owner = TeamIdentitySerializer(read_only=True, allow_null=True)


class TerritoryTurnSerializer(serializers.ModelSerializer):
    acting_player = TeamIdentitySerializer(read_only=True)
    target = serializers.SerializerMethodField()
    ownership_change = serializers.SerializerMethodField()

    class Meta:
        model = TerritoryTurn
        fields = (
            "number",
            "acting_player",
            "target",
            "target_value",
            "action_type",
            "dice_result",
            "success",
            "attacker_score_change",
            "defender_score_change",
            "ownership_change",
        )
        read_only_fields = fields

    @extend_schema_field(TerritoryTargetSerializer)
    def get_target(self, turn: TerritoryTurn) -> dict:
        return {"row": turn.target_row, "column": turn.target_column}

    @extend_schema_field(TerritoryOwnershipChangeSerializer)
    def get_ownership_change(self, turn: TerritoryTurn) -> dict:
        serializer = TeamIdentitySerializer
        return {
            "previous_owner": serializer(turn.previous_owner).data if turn.previous_owner else None,
            "new_owner": serializer(turn.new_owner).data if turn.new_owner else None,
        }


class TerritoryGameStateSerializer(serializers.ModelSerializer):
    players = serializers.SerializerMethodField()
    board = serializers.SerializerMethodField()
    active_player = TeamIdentitySerializer(read_only=True, allow_null=True)
    winner = TeamIdentitySerializer(read_only=True, allow_null=True)
    is_draw = serializers.SerializerMethodField()
    turns_remaining = serializers.IntegerField(read_only=True)
    previous_turn = serializers.SerializerMethodField()

    class Meta:
        model = TerritoryGame
        fields = (
            "id",
            "board",
            "players",
            "active_player",
            "turns_completed",
            "turns_remaining",
            "status",
            "winner",
            "is_draw",
            "previous_turn",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_players(self, game: TerritoryGame) -> list[dict]:
        return [
            {
                **TeamIdentitySerializer(game.player_one).data,
                "score": game.player_one_score,
                "has_selected_start": game.player_one_started,
            },
            {
                **TeamIdentitySerializer(game.player_two).data,
                "score": game.player_two_score,
                "has_selected_start": game.player_two_started,
            },
        ]

    def get_board(self, game: TerritoryGame) -> list[list[dict]]:
        board = [[] for _ in range(BOARD_SIZE)]
        for cell in game.cells.all():
            board[cell.row].append(TerritoryCellSerializer(cell).data)
        return board

    def get_is_draw(self, game: TerritoryGame) -> bool:
        return game.status == TerritoryGameStatus.FINISHED and game.winner_id is None

    @extend_schema_field(TerritoryTurnSerializer(allow_null=True))
    def get_previous_turn(self, game: TerritoryGame) -> dict | None:
        turns = list(game.turns.all())
        return TerritoryTurnSerializer(turns[-1]).data if turns else None


class CreateTerritoryGameSerializer(serializers.Serializer):
    player_one = serializers.SlugField(max_length=32)
    player_two = serializers.SlugField(max_length=32)

    def validate(self, attrs):
        if attrs["player_one"] == attrs["player_two"]:
            raise serializers.ValidationError("Two different teams are required.")
        return attrs


class PlayTerritoryTurnSerializer(serializers.Serializer):
    row = serializers.IntegerField(min_value=0, max_value=BOARD_SIZE - 1)
    column = serializers.IntegerField(min_value=0, max_value=BOARD_SIZE - 1)

    def to_internal_value(self, data):
        unexpected = set(data) - {"row", "column"}
        if unexpected:
            message = "This field is not accepted; the backend rolls the die."
            raise serializers.ValidationError({field: message for field in unexpected})
        return super().to_internal_value(data)


class CharityBagParticipationSerializer(serializers.ModelSerializer):
    team = TeamIdentitySerializer(read_only=True)

    class Meta:
        model = CharityBagParticipation
        fields = (
            "team",
            "action",
            "amount",
            "stake_deducted",
            "final_payout",
            "submitted_at",
            "settled_at",
        )
        read_only_fields = fields


class CharityBagEventSerializer(serializers.ModelSerializer):
    remaining_seconds = serializers.SerializerMethodField()
    can_participate = serializers.SerializerMethodField()
    my_participation = serializers.SerializerMethodField()
    participations = serializers.SerializerMethodField()

    class Meta:
        model = CharityBagEvent
        fields = (
            "id",
            "status",
            "starts_at",
            "ends_at",
            "remaining_seconds",
            "can_participate",
            "my_participation",
            "participations",
            "total_contributed",
            "total_requested",
            "charity_succeeded",
            "settlement_started_at",
            "settled_at",
        )
        read_only_fields = fields

    def get_remaining_seconds(self, event: CharityBagEvent) -> int:
        from django.utils import timezone

        if event.status != CharityBagStatus.ACTIVE:
            return 0
        return max(0, int((event.ends_at - timezone.now()).total_seconds()))

    def _user_team_id(self):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        return request.user.team_id

    def get_can_participate(self, event: CharityBagEvent) -> bool:
        team_id = self._user_team_id()
        return bool(
            team_id
            and event.status == CharityBagStatus.ACTIVE
            and not event.participations.filter(team_id=team_id).exists()
        )

    def get_my_participation(self, event: CharityBagEvent):
        team_id = self._user_team_id()
        if not team_id:
            return None
        entry = next(
            (row for row in event.participations.all() if row.team_id == team_id),
            None,
        )
        return CharityBagParticipationSerializer(entry).data if entry else None

    def get_participations(self, event: CharityBagEvent) -> list[dict]:
        if event.status != CharityBagStatus.FINISHED:
            return []
        return CharityBagParticipationSerializer(event.participations.all(), many=True).data

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.status != CharityBagStatus.FINISHED:
            data["total_contributed"] = None
            data["total_requested"] = None
            data["charity_succeeded"] = None
        return data


class EnterCharityBagSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("contribute", "request"))
    amount = serializers.IntegerField(min_value=1)


class CreateCharityBagSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)
    duration_seconds = serializers.IntegerField(required=False, min_value=1, max_value=3600)

    def validate(self, attrs):
        if attrs.get("ends_at") and attrs.get("duration_seconds"):
            raise serializers.ValidationError("Send either ends_at or duration_seconds, not both.")
        return attrs


class CentipedeDecisionSerializer(serializers.ModelSerializer):
    actor = TeamIdentitySerializer(read_only=True)

    class Meta:
        model = CentipedeDecision
        fields = (
            "sequence",
            "round_number",
            "actor",
            "action",
            "displayed_reward",
            "created_at",
        )
        read_only_fields = fields


class CentipedeGameSerializer(serializers.ModelSerializer):
    players = serializers.SerializerMethodField()
    active_player = TeamIdentitySerializer(read_only=True, allow_null=True)
    winner = TeamIdentitySerializer(read_only=True, allow_null=True)
    history = serializers.SerializerMethodField()

    class Meta:
        model = CentipedeGame
        fields = (
            "id",
            "players",
            "round_number",
            "active_player",
            "actions_completed",
            "status",
            "winner",
            "history",
            "finished_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_players(self, game: CentipedeGame) -> list[dict]:
        return [
            {
                **TeamIdentitySerializer(game.player_one).data,
                "position": 1,
                "current_reward": game.player_one_reward,
                "final_payout": game.player_one_final_payout,
            },
            {
                **TeamIdentitySerializer(game.player_two).data,
                "position": 2,
                "current_reward": game.player_two_reward,
                "final_payout": game.player_two_final_payout,
            },
        ]

    def get_history(self, game: CentipedeGame) -> list[dict]:
        return CentipedeDecisionSerializer(game.decisions.all(), many=True).data


class CreateCentipedeGameSerializer(serializers.Serializer):
    player_one = serializers.SlugField(max_length=32)
    player_two = serializers.SlugField(max_length=32)

    def validate(self, attrs):
        if attrs["player_one"] == attrs["player_two"]:
            raise serializers.ValidationError("Two different teams are required.")
        return attrs


class PlayCentipedeActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("take", "continue"))

    def to_internal_value(self, data):
        unexpected = set(data) - {"action"}
        if unexpected:
            raise serializers.ValidationError(
                {
                    field: "Reward and balance values are calculated by the backend."
                    for field in unexpected
                }
            )
        return super().to_internal_value(data)


class OlympicsScoringZoneSerializer(serializers.Serializer):
    code = serializers.SlugField(max_length=32)
    label = serializers.CharField(max_length=64)
    score = serializers.IntegerField(min_value=0, max_value=100000)


class OlympicsResultSerializer(serializers.ModelSerializer):
    recorded_by = serializers.CharField(source="recorded_by.username", read_only=True)

    class Meta:
        model = OlympicsResult
        fields = (
            "request_id",
            "round_number",
            "player_one_attempts",
            "player_two_attempts",
            "player_one_total",
            "player_two_total",
            "player_one_best_distance",
            "player_two_best_distance",
            "outcome",
            "recorded_by",
            "created_at",
        )
        read_only_fields = fields


class OlympicsMatchSerializer(serializers.ModelSerializer):
    players = serializers.SerializerMethodField()
    winner = TeamIdentitySerializer(read_only=True, allow_null=True)
    results = OlympicsResultSerializer(many=True, read_only=True)
    tiebreak_occurred = serializers.SerializerMethodField()

    class Meta:
        model = OlympicsMatch
        fields = (
            "id",
            "mini_game",
            "players",
            "scoring_zones",
            "status",
            "tiebreak_occurred",
            "winner",
            "results",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_players(self, match: OlympicsMatch) -> list[dict]:
        return [
            {**TeamIdentitySerializer(match.player_one).data, "position": 1},
            {**TeamIdentitySerializer(match.player_two).data, "position": 2},
        ]

    def get_tiebreak_occurred(self, match: OlympicsMatch) -> bool:
        return match.results.count() > 1 or match.status == "tiebreak"


class CreateOlympicsMatchSerializer(serializers.Serializer):
    mini_game = serializers.ChoiceField(choices=OlympicsMiniGame.values)
    player_one = serializers.SlugField(max_length=32)
    player_two = serializers.SlugField(max_length=32)
    scoring_zones = OlympicsScoringZoneSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        if attrs["player_one"] == attrs["player_two"]:
            raise serializers.ValidationError("Two different teams are required.")
        return attrs


class RecordOlympicsResultSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    winner = serializers.SlugField(max_length=32, required=False, allow_null=True)
    is_tie = serializers.BooleanField(default=False)
    player_one_best_distance = serializers.DecimalField(
        max_digits=9,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=0,
    )
    player_two_best_distance = serializers.DecimalField(
        max_digits=9,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=0,
    )
    player_one_attempts = serializers.ListField(
        child=serializers.JSONField(), required=False, default=list
    )
    player_two_attempts = serializers.ListField(
        child=serializers.JSONField(), required=False, default=list
    )

    def to_internal_value(self, data):
        allowed = set(self.fields)
        unexpected = set(data) - allowed
        if unexpected:
            raise serializers.ValidationError(
                {field: "This physical result field is not accepted." for field in unexpected}
            )
        return super().to_internal_value(data)


class AuctionBidSerializer(serializers.ModelSerializer):
    team = TeamIdentitySerializer(read_only=True)

    class Meta:
        model = AuctionBid
        fields = ("sequence", "team", "amount", "created_at")


class AuctionPairSerializer(serializers.ModelSerializer):
    team_one = TeamIdentitySerializer(read_only=True)
    team_two = TeamIdentitySerializer(read_only=True, allow_null=True)
    highest_bidder = TeamIdentitySerializer(read_only=True, allow_null=True)
    winner = TeamIdentitySerializer(read_only=True, allow_null=True)
    bids = AuctionBidSerializer(many=True, read_only=True)

    class Meta:
        model = AuctionPair
        fields = (
            "id",
            "team_one",
            "team_two",
            "rank_one",
            "rank_two",
            "team_one_bid",
            "team_two_bid",
            "highest_bid",
            "highest_bidder",
            "winner",
            "status",
            "automatic_award",
            "settled_at",
            "bids",
        )


class AuctionEventSerializer(serializers.ModelSerializer):
    pairs = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model = AuctionEvent
        fields = (
            "id",
            "status",
            "reward",
            "opening_bid",
            "duration_seconds",
            "ranking_snapshot",
            "starts_at",
            "ends_at",
            "remaining_seconds",
            "settled_at",
            "pairs",
        )

    def get_pairs(self, event):
        request = self.context.get("request")
        pairs = event.pairs.all()
        if request and not request.user.has_perm("game.act_as_mentor"):
            pairs = [
                pair
                for pair in pairs
                if request.user.team_id in (pair.team_one_id, pair.team_two_id)
            ]
        return AuctionPairSerializer(pairs, many=True).data

    def get_remaining_seconds(self, event):
        return max(0, int((event.ends_at - timezone.now()).total_seconds()))


class CreateAuctionEventSerializer(serializers.Serializer):
    duration_seconds = serializers.IntegerField(min_value=1, default=600)


class PlaceAuctionBidSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    amount = serializers.IntegerField(min_value=1)


class WheelPrizeConfigSerializer(serializers.Serializer):
    code = serializers.SlugField(max_length=32)
    prize_type = serializers.ChoiceField(choices=WheelPrizeType.values)
    display_name = serializers.CharField(max_length=100)
    glorium_amount = serializers.IntegerField(min_value=0, default=0)
    reward_data = serializers.JSONField(default=dict)
    weight = serializers.IntegerField(min_value=1)
    available = serializers.BooleanField(default=True)
    stock = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class WheelSpinSerializer(serializers.ModelSerializer):
    team = TeamIdentitySerializer(read_only=True)

    class Meta:
        model = WheelSpin
        fields = (
            "id",
            "request_id",
            "team",
            "spin_cost",
            "prize_type",
            "prize_name",
            "glorium_payout",
            "delivery_status",
            "created_at",
            "delivered_at",
        )


class WheelEventSerializer(serializers.ModelSerializer):
    prizes = serializers.SerializerMethodField()
    spins = serializers.SerializerMethodField()
    grand_prize_winner = TeamIdentitySerializer(read_only=True, allow_null=True)
    spins_available = serializers.SerializerMethodField()

    class Meta:
        model = WheelEvent
        fields = (
            "id",
            "status",
            "spin_cost",
            "total_collected",
            "grand_prize_winner",
            "spins_available",
            "prizes",
            "spins",
            "started_at",
            "finished_at",
        )

    def get_spins_available(self, event):
        return event.status == "active"

    def get_prizes(self, event):
        request = self.context.get("request")
        mentor = request and request.user.has_perm("game.act_as_mentor")
        return [
            {
                "code": prize.code,
                "prize_type": prize.prize_type,
                "display_name": prize.display_name,
                "glorium_amount": prize.glorium_amount,
                "available": prize.available,
                "stock": prize.stock if mentor else None,
                **({"weight": prize.weight} if mentor else {}),
            }
            for prize in event.prizes.all()
        ]

    def get_spins(self, event):
        request = self.context.get("request")
        spins = event.spins.all()
        if request and not request.user.has_perm("game.act_as_mentor"):
            spins = [spin for spin in spins if spin.team_id == request.user.team_id]
        return WheelSpinSerializer(spins, many=True).data


class CreateWheelEventSerializer(serializers.Serializer):
    spin_cost = serializers.IntegerField(min_value=1, default=10)
    prizes = WheelPrizeConfigSerializer(many=True)


class SpinWheelSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()


class PigRollSerializer(serializers.ModelSerializer):
    class Meta:
        model = PigRoll
        fields = ("number", "dice_result", "amount_added", "pot_after", "created_at")


class PigGameSerializer(serializers.ModelSerializer):
    team = TeamIdentitySerializer(read_only=True)
    rolls = PigRollSerializer(many=True, read_only=True)

    class Meta:
        model = PigGame
        fields = (
            "id",
            "event_id",
            "team",
            "entry_fee",
            "max_pot",
            "pot",
            "rolls_count",
            "status",
            "final_payout",
            "started_at",
            "finished_at",
            "rolls",
        )


class PigEventSerializer(serializers.ModelSerializer):
    games = serializers.SerializerMethodField()

    class Meta:
        model = PigEvent
        fields = ("id", "status", "entry_fee", "max_pot", "created_at", "finished_at", "games")

    def get_games(self, event):
        request = self.context.get("request")
        games = event.games.all()
        if request and not request.user.has_perm("game.act_as_mentor"):
            games = [game for game in games if game.team_id == request.user.team_id]
        return PigGameSerializer(games, many=True).data


class CreatePigEventSerializer(serializers.Serializer):
    max_pot = serializers.IntegerField(min_value=1)


class PigActionSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=("roll", "cash_out"))
