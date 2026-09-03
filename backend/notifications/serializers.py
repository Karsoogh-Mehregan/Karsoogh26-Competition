from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.openapi import extend_schema_field
from teams.models import Team

from .models import Audience, Message, MessageStatus, Notification
from .services import SYSTEM_SENDER_LABEL, audience_size

User = get_user_model()


def _sender_name(message: Message) -> str:
    """What the card shows on its sender line.

    `sender_label` is stamped at send time precisely so this survives the
    account being renamed or deleted afterwards.
    """
    if message.sender_label:
        return message.sender_label
    if message.sender_id is not None:
        return message.sender.get_full_name() or message.sender.username
    return SYSTEM_SENDER_LABEL


class InboxItemSerializer(serializers.ModelSerializer):
    """One card in the bell panel. Flat on purpose — the card renders it whole.

    The body ships with the list rather than behind a second request: these are
    a couple of lines each, and an inbox that refetches on every expand feels
    broken on a hall's wifi.
    """

    title = serializers.CharField(source="message.title", read_only=True)
    body = serializers.CharField(source="message.body", read_only=True)
    excerpt = serializers.CharField(source="message.excerpt", read_only=True)
    kind = serializers.CharField(source="message.kind", read_only=True)
    event_key = serializers.CharField(source="message.event_key", read_only=True)
    sent_at = serializers.DateTimeField(source="message.sent_at", read_only=True)
    sender = serializers.SerializerMethodField()
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "title",
            "body",
            "excerpt",
            "kind",
            "event_key",
            "sender",
            "sent_at",
            "created_at",
            "is_read",
            "read_at",
        )

    def get_sender(self, obj: Notification) -> str:
        return _sender_name(obj.message)


class InboxSerializer(serializers.Serializer):
    """The panel's whole state in one response, so the bell's dot can never
    disagree with the list it opens."""

    unread = serializers.IntegerField(read_only=True)
    total = serializers.IntegerField(read_only=True)
    results = InboxItemSerializer(many=True, read_only=True)


class MarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class ReadResultSerializer(serializers.Serializer):
    marked = serializers.IntegerField(read_only=True)
    unread = serializers.IntegerField(read_only=True)


class AudienceChoiceSerializer(serializers.Serializer):
    value = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)


class AudienceTeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ("code", "name")


class AudienceUserSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    team_code = serializers.CharField(source="team.code", read_only=True, default=None)

    class Meta:
        model = User
        fields = ("id", "username", "label", "team_code")

    def get_label(self, user) -> str:
        full = user.get_full_name()
        return f"{full} ({user.username})" if full else user.username


class AudienceOptionsSerializer(serializers.Serializer):
    """Everything the recipient picker needs, in one call.

    Choice labels come from the server rather than being hardcoded in the SPA,
    so adding an audience stays a backend-only change.
    """

    choices = AudienceChoiceSerializer(many=True, read_only=True)
    teams = AudienceTeamSerializer(many=True, read_only=True)
    users = AudienceUserSerializer(many=True, read_only=True)


class MessageSerializer(serializers.ModelSerializer):
    """A row in Drafts or Sent."""

    sender = serializers.SerializerMethodField()
    audience_label = serializers.SerializerMethodField()
    audience_team = serializers.SlugRelatedField(slug_field="code", read_only=True)
    excerpt = serializers.CharField(read_only=True)
    recipient_count = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id",
            "kind",
            "status",
            "title",
            "body",
            "excerpt",
            "audience",
            "audience_label",
            "audience_team",
            "audience_user",
            "sender",
            "event_key",
            "created_at",
            "updated_at",
            "sent_at",
            "recipient_count",
            "read_count",
        )

    def get_sender(self, message: Message) -> str:
        return _sender_name(message)

    def get_audience_label(self, message: Message) -> str:
        if message.audience == Audience.TEAM and message.audience_team_id:
            return f"تیم {message.audience_team.name}"
        if message.audience == Audience.USER and message.audience_user_id:
            return message.audience_user.username
        return Audience(message.audience).label

    @extend_schema_field(int)
    def get_recipient_count(self, message: Message) -> int:
        """Delivered count once sent; the projected reach while still a draft."""
        if message.status != MessageStatus.SENT:
            return audience_size(message)
        annotated = getattr(message, "delivered_count", None)
        return annotated if annotated is not None else message.notifications.count()

    @extend_schema_field(int)
    def get_read_count(self, message: Message) -> int:
        if message.status != MessageStatus.SENT:
            return 0
        annotated = getattr(message, "opened_count", None)
        if annotated is not None:
            return annotated
        return message.notifications.filter(read_at__isnull=False).count()


class MessageWriteSerializer(serializers.ModelSerializer):
    """Compose or edit. `audience_team` is addressed by code, as everywhere else."""

    audience_team = serializers.SlugRelatedField(
        slug_field="code",
        queryset=Team.objects.all(),
        required=False,
        allow_null=True,
    )
    audience_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Message
        fields = ("title", "body", "audience", "audience_team", "audience_user")

    def validate(self, attrs):
        # A PATCH carries only what changed, so unset fields fall back to the row.
        current = self.instance
        audience = attrs.get("audience", getattr(current, "audience", Audience.ALL))
        team = attrs.get("audience_team", getattr(current, "audience_team", None))
        user = attrs.get("audience_user", getattr(current, "audience_user", None))

        if audience == Audience.TEAM and team is None:
            raise serializers.ValidationError({"audience_team": "یک تیم را انتخاب کنید."})
        if audience == Audience.USER and user is None:
            raise serializers.ValidationError({"audience_user": "یک گیرنده را انتخاب کنید."})

        # Clear the field the chosen audience does not use, so the database
        # constraint never has to reject something the API just accepted.
        attrs["audience_team"] = team if audience == Audience.TEAM else None
        attrs["audience_user"] = user if audience == Audience.USER else None
        return attrs


class SendResultSerializer(serializers.Serializer):
    message = MessageSerializer(read_only=True)
    delivered = serializers.IntegerField(read_only=True)
