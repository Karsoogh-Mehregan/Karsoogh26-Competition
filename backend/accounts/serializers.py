from rest_framework import serializers

from notifications.permissions import SEND_PERM as SEND_ANNOUNCEMENT_PERM

from .models import User
from .permissions import DESIGNER_PERM, DUEL_MENTOR_PERM, MENTOR_PERM, has_game_god_rights


class CsrfSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class MeSerializer(serializers.ModelSerializer):
    is_mentor = serializers.SerializerMethodField()
    is_game_god = serializers.SerializerMethodField()
    is_announcer = serializers.SerializerMethodField()
    is_designer = serializers.SerializerMethodField()
    is_duel_mentor = serializers.SerializerMethodField()
    team = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "is_staff",
            "is_mentor",
            "is_game_god",
            "is_announcer",
            "is_designer",
            "is_duel_mentor",
            "team",
        )

    def get_is_mentor(self, user: User) -> bool:
        return user.has_perm(MENTOR_PERM)

    def get_is_announcer(self, user: User) -> bool:
        """Its own flag, not `is_game_god`: sending is backed by the Notifier
        group, which an organiser may hand to anyone. The SPA must show the
        composer to exactly whoever the API would let through."""
        return user.has_perm(SEND_ANNOUNCEMENT_PERM)

    def get_is_game_god(self, user: User) -> bool:
        return has_game_god_rights(user)

    def get_is_designer(self, user: User) -> bool:
        return user.has_perm(DESIGNER_PERM)

    def get_is_duel_mentor(self, user: User) -> bool:
        """Judging duels is its own grant, like announcing — the SPA shows the
        winner picker on exactly what the API would accept."""
        return user.has_perm(DUEL_MENTOR_PERM)

    def get_team(self, user: User) -> dict | None:
        if user.team_id is None:
            return None
        return {
            "code": user.team.code,
            "name": user.team.name,
            "board": user.team.board,
        }
