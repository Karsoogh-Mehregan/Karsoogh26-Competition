from rest_framework import serializers

from teams.models import Team
from teams.serializers import TeamSerializer

from .models import User


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class MeSerializer(serializers.ModelSerializer):
    acting_team = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "is_staff", "acting_team")

    def get_acting_team(self, user):
        team = self.context.get("acting_team")
        if team is None:
            return None
        return TeamSerializer(team).data


class ActAsSerializer(serializers.Serializer):
    team = serializers.SlugRelatedField(
        slug_field="code",
        queryset=Team.objects.all(),
        allow_null=True,
    )
