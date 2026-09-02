from rest_framework import serializers

from .models import User
from .permissions import MENTOR_PERM, has_game_god_rights


class CsrfSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class MeSerializer(serializers.ModelSerializer):
    is_mentor = serializers.SerializerMethodField()
    is_game_god = serializers.SerializerMethodField()
    team = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "is_staff", "is_mentor", "is_game_god", "team")

    def get_is_mentor(self, user: User) -> bool:
        return user.has_perm(MENTOR_PERM)

    def get_is_game_god(self, user: User) -> bool:
        return has_game_god_rights(user)

    def get_team(self, user: User) -> dict | None:
        if user.team_id is None:
            return None
        return {"code": user.team.code, "name": user.team.name}
