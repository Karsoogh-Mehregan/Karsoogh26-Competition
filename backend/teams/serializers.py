from rest_framework import serializers

from game.models import Occupancy

from .models import Team


class HoldingSerializer(serializers.ModelSerializer):
    node_code = serializers.CharField(source="node.code", read_only=True)
    node_name = serializers.CharField(source="node.name", read_only=True)
    level = serializers.CharField(source="node.level_id", read_only=True)

    class Meta:
        model = Occupancy
        fields = ("id", "node_code", "node_name", "level", "slot", "floor")


class TeamSerializer(serializers.ModelSerializer):
    holdings = HoldingSerializer(many=True, read_only=True)

    class Meta:
        model = Team
        fields = ("code", "name", "balance", "holdings")
