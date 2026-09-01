from rest_framework import serializers

from accounts.permissions import MENTOR_PERM
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
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ("code", "name", "balance", "color", "holdings")

    def get_balance(self, team: Team) -> int | None:
        """Only mentors and the team itself see the number; other teams see null."""
        user = self.context["request"].user
        if user.has_perm(MENTOR_PERM) or user.team_id == team.pk:
            return team.balance
        return None


class LeaderboardRowSerializer(serializers.Serializer):
    rank = serializers.IntegerField(read_only=True)
    code = serializers.SlugField(read_only=True)
    name = serializers.CharField(read_only=True)
    balance = serializers.IntegerField(read_only=True)


class ClaimStartSerializer(serializers.Serializer):
    node = serializers.CharField(max_length=16)

    def validate_node(self, value):
        if color_for_start(value) is None:
            raise serializers.ValidationError("این نود یک خانهٔ شروع نیست.")
        return value
