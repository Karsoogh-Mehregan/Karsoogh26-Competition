from rest_framework import serializers

from .models import User
from .permissions import MENTOR_PERM


class CsrfSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class MeSerializer(serializers.ModelSerializer):
    is_mentor = serializers.SerializerMethodField()
    team = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "is_staff", "is_mentor", "team")

    def get_is_mentor(self, user: User) -> bool:
        return user.has_perm(MENTOR_PERM)

    def get_team(self, user: User) -> dict | None:
        if user.team_id is None:
            return None
        return {"code": user.team.code, "name": user.team.name}
