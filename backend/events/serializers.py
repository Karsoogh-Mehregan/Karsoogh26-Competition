from rest_framework import serializers

from core.openapi import extend_schema_field
from teams.models import Team

from .models import (
    BOARD_SIZE,
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
