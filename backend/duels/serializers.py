"""What a duel looks like over the wire.

The room link is the one field that is not public: it is a live meeting anyone
holding the URL can walk into, so `DuelSerializer` only renders it for the two
teams and the assigned judge. Everyone else — a mentor browsing, another team
reading a leaderboard — sees the duel with `room_link: null`.
"""

from rest_framework import serializers

from teams.models import Team

from .models import Duel, Room


class DuelTeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ("code", "name", "color")


class RoomSerializer(serializers.ModelSerializer):
    mentor = serializers.CharField(source="mentor.get_username", read_only=True)

    class Meta:
        model = Room
        fields = ("id", "name", "link", "mentor", "is_active", "last_assigned_at")


class DuelSerializer(serializers.ModelSerializer):
    attacker = DuelTeamSerializer(read_only=True)
    attacked = DuelTeamSerializer(read_only=True)
    winner = DuelTeamSerializer(read_only=True)
    loser = DuelTeamSerializer(read_only=True)
    node_code = serializers.CharField(source="node.code", read_only=True)
    node_name = serializers.CharField(source="node.name", read_only=True)
    level = serializers.CharField(source="node.level_id", read_only=True)
    mentor = serializers.CharField(source="mentor.get_username", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True)
    room_link = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Duel
        fields = (
            "id",
            "attacker",
            "attacked",
            "node_code",
            "node_name",
            "level",
            "floor",
            "stake",
            "status",
            "winner",
            "loser",
            "mentor",
            "room_name",
            "room_link",
            "my_role",
            "created_at",
            "resolved_at",
        )

    def _viewer(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def get_room_link(self, duel: Duel) -> str | None:
        """Only the people who are supposed to be in the meeting get the URL."""
        user = self._viewer()
        if user is None or not user.is_authenticated:
            return None
        if user.pk == duel.mentor_id:
            return duel.room.link
        if user.team_id in (duel.attacker_id, duel.attacked_id):
            return duel.room.link
        return None

    def get_my_role(self, duel: Duel) -> str | None:
        """`attacker`, `attacked`, `judge`, or nothing — so the UI stops branching."""
        user = self._viewer()
        if user is None or not user.is_authenticated:
            return None
        if user.pk == duel.mentor_id:
            return "judge"
        if user.team_id == duel.attacker_id:
            return "attacker"
        if user.team_id == duel.attacked_id:
            return "attacked"
        return None


class DuelTargetSerializer(serializers.Serializer):
    """One row of «تیم‌هایی که می‌توانید به آن‌ها دوئل بزنید»."""

    occupancy_id = serializers.IntegerField()
    node_code = serializers.CharField()
    node_name = serializers.CharField()
    level = serializers.CharField()
    floor = serializers.IntegerField()
    team = DuelTeamSerializer()
    cost = serializers.IntegerField()


class RequestDuelSerializer(serializers.Serializer):
    occupancy = serializers.IntegerField(help_text="Id of the seat being challenged.")


class ResolveDuelSerializer(serializers.Serializer):
    winner = serializers.SlugField(help_text="Team code of the winner.")
