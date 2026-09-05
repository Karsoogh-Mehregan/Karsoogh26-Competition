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
    # `main`'s names for the two lists; the toll-level filtering and the
    # per-status split are this branch's. A gate is not a holding — nobody owns
    # one and it has no capacity — so neither can travel in `holdings`.
    cleared_tolls = serializers.SerializerMethodField()
    active_tolls = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = (
            "code",
            "name",
            "balance",
            "color",
            "holdings",
            "cleared_tolls",
            "active_tolls",
        )

    def _toll_codes(self, team: Team, status: str) -> list[str]:
        """Toll nodes where this team has an attempt in ``status``.

        Reads the `_toll_attempts` prefetch that `Team.objects.with_holdings()`
        sets up, so the whole board costs one query; the fallback keeps a lone
        serializer (a test, a shell) honest. Non-toll boards are filtered out —
        a board an organiser hangs on a house is side content, and must not
        report as a crossing.
        """
        from game.models import Level

        rows = getattr(team, "_toll_attempts", None)
        if rows is not None:
            return sorted(
                {
                    row.game.node.code
                    for row in rows
                    if row.status == status and row.game.node.level_id == Level.TOLL
                }
            )
        from minesweeper.crossings import cleared_node_codes, open_board_node_codes
        from minesweeper.models import MinesweeperStatus

        if status == MinesweeperStatus.WON:
            return cleared_node_codes(team)
        return open_board_node_codes(team)

    def get_cleared_tolls(self, team: Team) -> list[str]:
        """Gates this team has beaten. This is what opens the road past them."""
        from minesweeper.models import MinesweeperStatus

        return self._toll_codes(team, MinesweeperStatus.WON)

    def get_active_tolls(self, team: Team) -> list[str]:
        """Gates with a board still open — paid for, so the map offers to resume
        it rather than quoting the toll again, and it reopens even if the holding
        the team reached the gate from has since been released."""
        from minesweeper.models import MinesweeperStatus

        return self._toll_codes(team, MinesweeperStatus.IN_PROGRESS)

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


# Every reason's Persian label, from the enum itself — a hand-written copy here
# fell behind the moment `event`, `duel` and `buyout` landed, and the wallet log
# showed the raw codes.
REASON_LABELS: dict[str, str] = dict(BalanceReason.choices)


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
    # A fake document names the storey it forges a deed to; gel takes the whole
    # house, so it never carries one.
    floor = serializers.IntegerField(required=False, allow_null=True, min_value=1)

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

        floor = attrs.get("floor")
        if item_type == ItemType.FAKE_DOCUMENT:
            if floor is None:
                raise serializers.ValidationError({"floor": "برای این آیتم باید طبقه مشخص شود."})
            attrs["floor"] = floor
        else:
            attrs["floor"] = None
        return attrs


class ClaimStartSerializer(serializers.Serializer):
    node = serializers.CharField(max_length=16)

    def validate_node(self, value):
        if color_for_start(value) is None:
            raise serializers.ValidationError("این نود یک خانهٔ شروع نیست.")
        return value
