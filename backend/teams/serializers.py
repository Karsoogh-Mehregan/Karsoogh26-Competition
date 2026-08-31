from rest_framework import serializers

from game.models import Occupancy

from .models import Team
from .start_colors import color_for_start


class HoldingSerializer(serializers.ModelSerializer):
    node_code = serializers.CharField(source="node.code", read_only=True)
    node_name = serializers.CharField(source="node.name", read_only=True)
    level = serializers.CharField(source="node.level_id", read_only=True)

    class Meta:
        model = Occupancy
        fields = ("id", "node_code", "node_name", "level", "slot", "floor", "grade", "is_spawn")


class TeamSerializer(serializers.ModelSerializer):
    holdings = HoldingSerializer(many=True, read_only=True)

    class Meta:
        model = Team
        fields = ("code", "name", "balance", "color", "holdings")


class ClaimStartSerializer(serializers.Serializer):
    node = serializers.CharField(max_length=16)

    def validate_node(self, value):
        if color_for_start(value) is None:
            raise serializers.ValidationError("این نود یک خانهٔ شروع نیست.")
        return value
