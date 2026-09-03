from rest_framework import serializers

from core.openapi import extend_schema_field
from game.models import Node
from minesweeper.models import MinesweeperAttempt, MinesweeperDifficulty, MinesweeperStatus


class CreateGameSerializer(serializers.Serializer):
    node = serializers.PrimaryKeyRelatedField(queryset=Node.objects.all())
    difficulty = serializers.ChoiceField(choices=MinesweeperDifficulty.choices)


class CellActionSerializer(serializers.Serializer):
    row = serializers.IntegerField()
    col = serializers.IntegerField()


class GameDefinitionSerializer(serializers.Serializer):
    """Staff create response — mine layout is not on the wire."""

    id = serializers.IntegerField(read_only=True)
    node = serializers.IntegerField(source="node_id", read_only=True)
    difficulty = serializers.CharField(read_only=True)
    width = serializers.IntegerField(read_only=True)
    height = serializers.IntegerField(read_only=True)
    mine_count = serializers.IntegerField(read_only=True)


def _public_cell(progress: dict, layout: dict, *, finished: bool) -> dict:
    """Build a client-safe cell. Hidden mines stay off the wire until the attempt ends."""
    if finished:
        return {
            "revealed": progress["revealed"],
            "flagged": progress["flagged"],
            "adjacent_mines": layout["adjacent_mines"],
            "mine": layout["mine"],
        }
    if progress["revealed"]:
        return {
            "revealed": True,
            "flagged": progress["flagged"],
            "adjacent_mines": layout["adjacent_mines"],
        }
    return {"revealed": False, "flagged": progress["flagged"]}


def public_board(attempt: MinesweeperAttempt) -> dict:
    finished = attempt.status != MinesweeperStatus.IN_PROGRESS
    layout_rows = attempt.game.board["cells"]
    progress_rows = attempt.board["cells"]
    return {
        "cells": [
            [
                _public_cell(progress, layout, finished=finished)
                for progress, layout in zip(progress_row, layout_row, strict=True)
            ]
            for progress_row, layout_row in zip(progress_rows, layout_rows, strict=True)
        ]
    }


class PublicGameSerializer(serializers.Serializer):
    """Public view of the caller's attempt, keyed by the reusable game id."""

    id = serializers.IntegerField(source="game_id", read_only=True)
    attempt_id = serializers.IntegerField(source="pk", read_only=True)
    node = serializers.IntegerField(source="game.node_id", read_only=True)
    difficulty = serializers.CharField(source="game.difficulty", read_only=True)
    width = serializers.IntegerField(source="game.width", read_only=True)
    height = serializers.IntegerField(source="game.height", read_only=True)
    mine_count = serializers.IntegerField(source="game.mine_count", read_only=True)
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
    def get_board(self, attempt: MinesweeperAttempt) -> dict:
        return public_board(attempt)
