"""An inbox for every user, filled two ways.

Automatically, by the game itself — a grade posted, an attempt burned, the
clock started — and by hand, when someone holding `send_announcement` writes a
message and picks an audience.

Two models, because "what was written" and "who has read it" have different
lifetimes. `Message` is the composed thing plus the audience it was aimed at;
`Notification` is one row per recipient, carrying the read state.

Fanning out at send time rather than matching the audience on every read is
deliberate. Read state needs a row per user anyway; an unread count then costs
one indexed query instead of an audience match per user; and a sent message
keeps the audience it *had* — a mentor added to the group an hour later must
not retroactively appear to have been addressed.
"""

from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.utils import timezone

TITLE_MAX = 120
EXCERPT_CHARS = 140


class Audience(models.TextChoices):
    """Who a message is aimed at. Resolved to users by `services.recipients_for`."""

    ALL = "all", "همه"
    TEAMS = "teams", "همهٔ تیم‌ها"
    MENTORS = "mentors", "همهٔ منتورها"
    DESIGNERS = "designers", "همهٔ طراحان"
    TEAM = "team", "یک تیم"
    USER = "user", "یک نفر"


class MessageKind(models.TextChoices):
    ANNOUNCEMENT = "announcement", "پیام مدیر"
    SYSTEM = "system", "خودکار"


class MessageStatus(models.TextChoices):
    DRAFT = "draft", "پیش‌نویس"
    SENT = "sent", "ارسال‌شده"


class Message(models.Model):
    """One composed message and the audience it was addressed to.

    A draft has no `Notification` rows at all: it exists only for its author
    until `services.send_message` fans it out.
    """

    kind = models.CharField(
        max_length=12, choices=MessageKind.choices, default=MessageKind.ANNOUNCEMENT
    )
    status = models.CharField(
        max_length=8, choices=MessageStatus.choices, default=MessageStatus.DRAFT
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_messages",
        help_text="Null for automatic messages: the game itself has no user row.",
    )
    sender_label = models.CharField(
        max_length=64,
        blank=True,
        help_text="What recipients see as the sender; survives the account being deleted.",
    )

    audience = models.CharField(max_length=12, choices=Audience.choices, default=Audience.ALL)
    audience_team = models.ForeignKey(
        "teams.Team",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="addressed_messages",
    )
    audience_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="addressed_messages",
    )

    title = models.CharField(max_length=TITLE_MAX)
    body = models.TextField(blank=True)

    # What happened, for automatic messages: `grade.posted`, `game.status`, …
    # The SPA picks an icon from it; empty on a hand-written announcement.
    event_key = models.SlugField(max_length=32, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        # Sending is its own right: narrower than running the game, and nothing
        # to do with grading. Seeded onto GameGods in 0002, grantable to anyone
        # else from the admin.
        permissions = [("send_announcement", "Can send announcements")]
        constraints = [
            # A team-addressed message needs a team, and only a team-addressed
            # one may carry it. Same for a single user.
            CheckConstraint(
                condition=(
                    Q(audience=Audience.TEAM, audience_team__isnull=False)
                    | (~Q(audience=Audience.TEAM) & Q(audience_team__isnull=True))
                ),
                name="message_team_audience_has_team",
            ),
            CheckConstraint(
                condition=(
                    Q(audience=Audience.USER, audience_user__isnull=False)
                    | (~Q(audience=Audience.USER) & Q(audience_user__isnull=True))
                ),
                name="message_user_audience_has_user",
            ),
            CheckConstraint(
                condition=(
                    Q(status=MessageStatus.DRAFT, sent_at__isnull=True)
                    | Q(status=MessageStatus.SENT, sent_at__isnull=False)
                ),
                name="message_sent_has_timestamp",
            ),
            # The game never writes a draft: an automatic message describes
            # something that already happened.
            CheckConstraint(
                condition=~Q(kind=MessageKind.SYSTEM) | Q(status=MessageStatus.SENT),
                name="message_system_is_never_draft",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="message_status_recent_idx"),
        ]

    def __str__(self):
        return self.title

    @property
    def is_draft(self) -> bool:
        return self.status == MessageStatus.DRAFT

    @property
    def excerpt(self) -> str:
        """The one-line preview the inbox card shows under the title."""
        flat = " ".join(self.body.split())
        if len(flat) <= EXCERPT_CHARS:
            return flat
        return flat[: EXCERPT_CHARS - 1].rstrip() + "…"


class NotificationQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(read_at__isnull=True)

    def for_user(self, user):
        return self.filter(user=user)

    def inbox(self):
        """Everything the panel needs to render a card, in one query."""
        return self.select_related("message", "message__sender").order_by("-id")


class Notification(models.Model):
    """One message, as delivered to one person. Read state lives here."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]
        constraints = [
            UniqueConstraint(fields=["message", "user"], name="notification_once_per_user"),
        ]
        indexes = [
            # The bell's red dot: count unread for one user.
            models.Index(
                fields=["user"],
                condition=Q(read_at__isnull=True),
                name="notification_unread_idx",
            ),
            models.Index(fields=["user", "-id"], name="notification_inbox_idx"),
        ]

    def __str__(self):
        return f"{self.message.title} -> {self.user}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self) -> bool:
        """Idempotent: re-reading a message does not move its timestamp."""
        if self.read_at is not None:
            return False
        self.read_at = timezone.now()
        self.save(update_fields=["read_at"])
        return True
