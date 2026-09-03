from django.contrib.auth import get_user_model
from rest_framework import serializers

from core.openapi import extend_schema_field
from teams.models import Team

from .models import AudienceScope, Message, MessageStatus, Notification
from .services import SYSTEM_SENDER_LABEL, audience_size, describe_audience

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
    teams = serializers.SlugRelatedField(slug_field="code", many=True, read_only=True)
    users = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
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
            "scopes",
            "teams",
            "users",
            "audience_label",
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
        return describe_audience(message)

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


# The three ways to name recipients, shared verbatim by the composer and the
# audience preview. Built fresh per serializer: a Field instance binds to its
# parent, so one shared object cannot sit on two of them.
def _scopes_field():
    return serializers.ListField(
        child=serializers.ChoiceField(choices=AudienceScope.choices),
        required=False,
        allow_empty=True,
    )


def _teams_field():
    return serializers.SlugRelatedField(
        slug_field="code", queryset=Team.objects.all(), many=True, required=False
    )


def _users_field():
    return serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True), many=True, required=False
    )


def _canonical_scopes(value):
    """Order and repeats carry no meaning; store one canonical form so two
    equivalent selections compare equal."""
    chosen = set(value)
    return [scope for scope in AudienceScope.values if scope in chosen]


class AudienceSelectionSerializer(serializers.Serializer):
    """Just the audience, for "how many would this reach?" before saving."""

    scopes = _scopes_field()
    teams = _teams_field()
    users = _users_field()

    def validate_scopes(self, value):
        return _canonical_scopes(value)


class MessageWriteSerializer(serializers.ModelSerializer):
    """Compose or edit.

    An empty audience is allowed here on purpose: you write the message first
    and decide who reads it after. Sending with nothing selected is what gets
    refused, in `MessageSendView`.
    """

    scopes = _scopes_field()
    teams = _teams_field()
    users = _users_field()

    class Meta:
        model = Message
        fields = ("title", "body", "scopes", "teams", "users")

    def validate_scopes(self, value):
        return _canonical_scopes(value)


class SendResultSerializer(serializers.Serializer):
    message = MessageSerializer(read_only=True)
    delivered = serializers.IntegerField(read_only=True)


class AudiencePreviewSerializer(serializers.Serializer):
    """What a selection would reach, before anything is written."""

    count = serializers.IntegerField(read_only=True)
    label = serializers.CharField(read_only=True)
