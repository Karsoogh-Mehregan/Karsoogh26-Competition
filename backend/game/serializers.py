from rest_framework import serializers

from .models import Occupancy
from .services import MENTOR_RELEASE_REASONS


class TeamSummarySerializer(serializers.Serializer):
    code = serializers.SlugField(read_only=True)
    name = serializers.CharField(read_only=True)
    balance = serializers.IntegerField(read_only=True)


class NodeSummarySerializer(serializers.Serializer):
    code = serializers.SlugField(read_only=True)
    name = serializers.CharField(read_only=True)
    level = serializers.CharField(source="level_id", read_only=True)


class HoldingSerializer(serializers.ModelSerializer):
    team = TeamSummarySerializer(read_only=True)
    node = NodeSummarySerializer(read_only=True)
    points = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Occupancy
        fields = (
            "team",
            "node",
            "slot",
            "floor",
            "grade",
            "grade_multiplier",
            "points",
            "question_assigned_at",
            "expires_at",
            "is_expired",
            "entered_at",
            "released_at",
            "release_reason",
        )
        read_only_fields = fields


class AssignQuestionSerializer(serializers.Serializer):
    """No input — the team and node come from the URL."""


class GradeSerializer(serializers.Serializer):
    grade = serializers.IntegerField(min_value=0, max_value=100)


class ReleaseSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(
        choices=[(reason.value, reason.label) for reason in MENTOR_RELEASE_REASONS]
    )
