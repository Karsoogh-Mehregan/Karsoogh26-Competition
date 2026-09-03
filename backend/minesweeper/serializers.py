from rest_framework import serializers

from core.openapi import extend_schema_field
from game.models import Node
from minesweeper.models import MinesweeperDifficulty, MinesweeperGame, MinesweeperStatus


class CreateGameSerializer(serializers.Serializer):
    node = serializers.PrimaryKeyRelatedField(queryset=Node.objects.all())
    difficulty = serializers.ChoiceField(choices=MinesweeperDifficulty.choices)


class CellActionSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    col = serializers.IntegerField()


def _public_cell(cell: dict, *, finished: bool) -> dict:
    """Build a client-safe cell. Hidden mines stay off the wire until the game ends."""
    if finished:
        return {
            "revealed": cell["revealed"],
            "flagged": cell["flagged"],
            "adjacent_mines": cell["adjacent_mines"],
            "mine": cell["mine"],
        }
    if cell["revealed"]:
        return {
            "revealed": True,
            "flagged": cell["flagged"],
            "adjacent_mines": cell["adjacent_mines"],
        }
    return {"revealed": False, "flagged": cell["flagged"]}


def public_board(game: MinesweeperGame) -> dict:
    finished = game.status != MinesweeperStatus.IN_PROGRESS
    return {
        "cells": [
            [_public_cell(cell, finished=finished) for cell in row] for row in game.board["cells"]
        ]
    }


class PublicGameSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    node = serializers.IntegerField(source="node_id", read_only=True)
    difficulty = serializers.CharField(read_only=True)
    width = serializers.IntegerField(read_only=True)
    height = serializers.IntegerField(read_only=True)
    mine_count = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    score = serializers.IntegerField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True)
    finished_at = serializers.DateTimeField(read_only=True, allow_null=True)
    board = serializers.SerializerMethodField()

    @extend_schema_field(
        {
            "type": "object",
            "properties": {
                "cells": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "object"}},
                }
            },
        }
    )
    def get_board(self, game: MinesweeperGame) -> dict:
        return public_board(game)
