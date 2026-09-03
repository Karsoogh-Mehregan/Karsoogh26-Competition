"""Composing, addressing and delivering messages.

The mechanism only. The wording of the automatic messages lives in
`notifications/alerts.py`, so game code calls something named after what
happened and never has to know how delivery works.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from game.services.events import NOTIFICATION_CREATED, publish_on_commit

from .models import Audience, Message, MessageKind, MessageStatus, Notification

logger = logging.getLogger("karsoogh")

User = get_user_model()

MENTOR_PERM = "game.act_as_mentor"
DESIGNER_PERM = "game.design_map"
SEND_PERM = "notifications.send_announcement"

SYSTEM_SENDER_LABEL = "سامانه"


def users_with_perm(perm: str) -> QuerySet:
    """Everyone explicitly granted `perm`, through a group or directly.

    Deliberately not `user.has_perm()`, which is True for every superuser:
    this answers "who is a mentor", not "who is allowed to act as one", and a
    superuser who is not actually mentoring should not be handed two hundred
    mentor notices. Same reasoning as `accounts.permissions.has_game_god_rights`.

    A permission that does not exist yet — `design_map` arrives with the
    designer work — simply matches nobody, rather than raising.
    """
    app_label, _, codename = perm.partition(".")
    return User.objects.filter(
        Q(
            groups__permissions__codename=codename,
            groups__permissions__content_type__app_label=app_label,
        )
        | Q(
            user_permissions__codename=codename,
            user_permissions__content_type__app_label=app_label,
        )
    ).distinct()


def recipients_for(message: Message) -> QuerySet:
    """Resolve a message's audience to the users who should receive it.

    The author is dropped: an announcement lands in the Sent folder, not in
    its own writer's inbox.
    """
    active = User.objects.filter(is_active=True)

    if message.audience == Audience.ALL:
        recipients = active
    elif message.audience == Audience.TEAMS:
        recipients = active.filter(team__isnull=False)
    elif message.audience == Audience.MENTORS:
        recipients = active.filter(pk__in=users_with_perm(MENTOR_PERM))
    elif message.audience == Audience.DESIGNERS:
        recipients = active.filter(pk__in=users_with_perm(DESIGNER_PERM))
    elif message.audience == Audience.TEAM:
        recipients = active.filter(team_id=message.audience_team_id)
    elif message.audience == Audience.USER:
        recipients = active.filter(pk=message.audience_user_id)
    else:
        raise ValueError(f"Unknown audience {message.audience!r}")

    if message.sender_id is not None:
        recipients = recipients.exclude(pk=message.sender_id)
    return recipients


def audience_size(message: Message) -> int:
    """How many people a message would reach — shown before sending."""
    return recipients_for(message).count()


@transaction.atomic
def send_message(message: Message) -> int:
    """Fan a message out to its audience. Idempotent, and safe to retry.

    Returns how many people it actually reached, which is what the composer
    reports back — "sent" with no number hides an audience that was empty.
    """
    message = Message.objects.select_for_update().get(pk=message.pk)

    user_ids = list(recipients_for(message).values_list("pk", flat=True))
    if user_ids:
        Notification.objects.bulk_create(
            (Notification(message=message, user_id=user_id) for user_id in user_ids),
            ignore_conflicts=True,
        )

    if message.status != MessageStatus.SENT:
        message.status = MessageStatus.SENT
        message.sent_at = timezone.now()
        message.save(update_fields=["status", "sent_at"])

    if user_ids:
        # Routing, not payload: `recipients` filters the frame server-side, so
        # nobody learns who else was addressed. The frame is a hint like every
        # other one — the client refetches its own inbox.
        publish_on_commit(
            NOTIFICATION_CREATED,
            {"title": message.title, "kind": message.kind},
            recipients=user_ids,
        )

    logger.info(
        "Message %s (%s) sent to %d recipient(s)", message.pk, message.audience, len(user_ids)
    )
    return len(user_ids)


def announce(
    *,
    title: str,
    body: str = "",
    audience: str = Audience.ALL,
    audience_team=None,
    audience_user=None,
    event_key: str = "",
    sender=None,
    sender_label: str = "",
) -> Message:
    """Write a message and send it in one step. The automatic path.

    `alerts.py` is the only caller worth reading; everything hand-written goes
    through the API, which creates a draft first.
    """
    message = Message.objects.create(
        kind=MessageKind.SYSTEM if sender is None else MessageKind.ANNOUNCEMENT,
        status=MessageStatus.SENT,
        sent_at=timezone.now(),
        sender=sender,
        sender_label=sender_label or (SYSTEM_SENDER_LABEL if sender is None else ""),
        audience=audience,
        audience_team=audience_team,
        audience_user=audience_user,
        title=title,
        body=body,
        event_key=event_key,
    )
    send_message(message)
    return message


# ---- inbox -----------------------------------------------------------------


def unread_count(user) -> int:
    return Notification.objects.for_user(user).unread().count()


def inbox(user, *, limit: int, unread_only: bool = False) -> list[Notification]:
    rows = Notification.objects.for_user(user).inbox()
    if unread_only:
        rows = rows.unread()
    return list(rows[:limit])


def mark_read(user, notification_ids: list[int]) -> int:
    """Mark the caller's own notifications read. Never touches anyone else's."""
    return (
        Notification.objects.for_user(user)
        .unread()
        .filter(pk__in=notification_ids)
        .update(read_at=timezone.now())
    )


def mark_all_read(user) -> int:
    return Notification.objects.for_user(user).unread().update(read_at=timezone.now())
