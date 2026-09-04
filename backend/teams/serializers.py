from rest_framework import serializers

from accounts.permissions import MENTOR_PERM
from game.models import Occupancy

from .models import BalanceEvent, BalanceReason, ItemType, Team, TeamItem
from .start_colors import color_for_start


class HoldingSerializer(serializers.ModelSerializer):
    node_code = serializers.CharField(source="node.code", read_only=True)
    node_name = serializers.CharField(source="node.name", read_only=True)
    level = serializers.CharField(source="node.level_id", read_only=True)

    class Meta:
        model = Occupancy
        fields = (
            "id",
            "node_code",
            "node_name",
            "level",
            "slot",
            "floor",
            "grade",
            "is_spawn",
            "source",
        )


class TeamSerializer(serializers.ModelSerializer):
    holdings = HoldingSerializer(many=True, read_only=True)
    balance = serializers.SerializerMethodField()
    crossings = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ("code", "name", "balance", "color", "holdings", "crossings")

    def get_crossings(self, team: Team) -> list[str]:
        """Toll gates this team has beaten, which is what opens the road past them.

        A gate is not a holding — nobody owns it and it has no capacity — so it
        cannot travel in `holdings`. The whole board's crossings are resolved in
        one query by `teams.board_cache` and passed in through the context; the
        fallback keeps a lone serializer (a test, a shell) honest.
        """
        by_team = self.context.get("crossings")
        if by_team is None:
            from minesweeper.crossings import cleared_node_codes

            return cleared_node_codes(team)
        return by_team.get(team.pk, [])

    def get_balance(self, team: Team) -> int | None:
        """Only mentors and the team itself see the number; other teams see null.

        `unmasked` renders the shared snapshot in teams.board_cache, which then
        masks per viewer; it must never be set on a response serializer.
        """
        if self.context.get("unmasked"):
            return team.balance
        user = self.context["request"].user
        if user.has_perm(MENTOR_PERM) or user.team_id == team.pk:
            return team.balance
        return None


class LeaderboardRowSerializer(serializers.Serializer):
    rank = serializers.IntegerField(read_only=True)
    code = serializers.SlugField(read_only=True)
    name = serializers.CharField(read_only=True)
    balance = serializers.IntegerField(read_only=True)


REASON_LABELS: dict[str, str] = {
    BalanceReason.INITIAL: "موجودی اولیه",
    BalanceReason.ENTRY: "رزرو خانه",
    BalanceReason.TOLL: "عوارضی",
    BalanceReason.GRADE: "نمره خانه",
}


class BalanceEventSerializer(serializers.ModelSerializer):
    reason_label = serializers.SerializerMethodField()

    class Meta:
        model = BalanceEvent
        fields = ("id", "delta", "balance_after", "reason", "reason_label", "detail", "created_at")

    def get_reason_label(self, obj: BalanceEvent) -> str:
        return REASON_LABELS.get(obj.reason, obj.reason)


class TeamItemSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source="get_item_type_display", read_only=True)

    class Meta:
        model = TeamItem
        fields = ("item_type", "quantity", "display_name")


_NODE_ITEMS = frozenset({ItemType.FAKE_DOCUMENT, ItemType.GEL})


class UseItemSerializer(serializers.Serializer):
    item_type = serializers.ChoiceField(choices=ItemType.choices)
    node_code = serializers.SlugField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        item_type = attrs["item_type"]
        node_code = attrs.get("node_code") or None
        if item_type in _NODE_ITEMS:
            if not node_code:
                raise serializers.ValidationError(
                    {"node_code": "برای این آیتم باید خانه مشخص شود."}
                )
            attrs["node_code"] = node_code
        else:
            attrs["node_code"] = None
        return attrs


class ClaimStartSerializer(serializers.Serializer):
    node = serializers.CharField(max_length=16)

    def validate_node(self, value):
        if color_for_start(value) is None:
            raise serializers.ValidationError("این نود یک خانهٔ شروع نیست.")
        return value
