from rest_framework import serializers

from .models import Team
from .start_colors import color_for_start


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ("code", "name", "balance", "color")


class ClaimStartSerializer(serializers.Serializer):
    node = serializers.CharField(max_length=16)

    def validate_node(self, value):
        if color_for_start(value) is None:
            raise serializers.ValidationError("این نود یک خانهٔ شروع نیست.")
        return value
