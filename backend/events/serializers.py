from rest_framework import serializers

from core.openapi import extend_schema_field
from teams.models import Team

from .models import (
    BOARD_SIZE,
    CharityBagEvent,
    CharityBagParticipation,
    CharityBagStatus,
    TerritoryCell,
    TerritoryGame,
    TerritoryGameStatus,
    TerritoryTurn,
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
