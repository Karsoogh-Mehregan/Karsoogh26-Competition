"""Composing, addressing and delivering messages.

Every message here is hand-written by an announcer through the API: a draft
first, then `send_message` fans it out. Nothing in `game/` writes to the inbox.
"""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from game.services.events import NOTIFICATION_CREATED, publish_on_commit

from .models import AudienceScope, Message, MessageStatus, Notification

logger = logging.getLogger("karsoogh")

User = get_user_model()

MENTOR_PERM = "game.act_as_mentor"
DESIGNER_PERM = "game.design_map"
SEND_PERM = "notifications.send_announcement"


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


SCOPE_FILTERS = {
    AudienceScope.TEAMS: lambda: Q(team__isnull=False),
    AudienceScope.MENTORS: lambda: Q(pk__in=users_with_perm(MENTOR_PERM)),
    AudienceScope.DESIGNERS: lambda: Q(pk__in=users_with_perm(DESIGNER_PERM)),
}


def resolve_audience(
    *,
    scopes,
    team_ids=(),
    user_ids=(),
    sender_id=None,
) -> QuerySet:
    """The audience rule itself, over plain values.

    Separate from `recipients_for` so the composer's preview can ask about a
    selection that has not been saved yet — an unsaved Message has no primary
    key, and so no M2M to read.
    """
    active = User.objects.filter(is_active=True)
    scopes = set(scopes or [])

    if AudienceScope.ALL in scopes:
        recipients = active
    else:
        # Start from "nobody" and widen. A bare Q() would match *everyone*,
        # which is the one wrong answer that looks like it works.
        condition = Q(pk__in=[])
        matched = False

        for scope, make_filter in SCOPE_FILTERS.items():
            if scope in scopes:
                condition |= make_filter()
                matched = True

        if team_ids:
            condition |= Q(team_id__in=team_ids)
            matched = True

        if user_ids:
            condition |= Q(pk__in=user_ids)
            matched = True

        if not matched:
            return active.none()
        recipients = active.filter(condition).distinct()

    if sender_id is not None:
        recipients = recipients.exclude(pk=sender_id)
    return recipients


def recipients_for(message: Message) -> QuerySet:
    """Resolve a saved message's audience to the users who should receive it.

    The union of three independent selections — named scopes, named teams,
    named people — so "these four teams, plus every mentor" is one message.
    Overlap is fine: the query is distinct, and the fan-out ignores conflicts
    anyway.

    The author is dropped: an announcement lands in the Sent folder, not in its
    own writer's inbox.
    """
    return resolve_audience(
        scopes=message.scopes,
        team_ids=list(message.teams.values_list("pk", flat=True)),
        user_ids=list(message.users.values_list("pk", flat=True)),
        sender_id=message.sender_id,
    )


def preview_audience(message: Message, *, teams=(), users=()) -> tuple[int, str]:
    """Reach and label for a selection that may not have been saved yet."""
    team_ids = [team.pk for team in teams]
    user_ids = [user.pk for user in users]
    count = resolve_audience(
        scopes=message.scopes,
        team_ids=team_ids,
        user_ids=user_ids,
        sender_id=message.sender_id,
    ).count()
    return count, describe_selection(
        scopes=message.scopes,
        team_names=[team.name for team in teams],
        usernames=[user.username for user in users],
    )


def describe_selection(*, scopes, team_names=(), usernames=()) -> str:
    """A human summary of an audience: "همهٔ منتورها، ۳ تیم".

    Names one team or one person outright, and counts them past that — a list
    of eight team names is not a label any more.
    """
    chosen = set(scopes or [])
    if AudienceScope.ALL in chosen:
        return AudienceScope.ALL.label

    parts = [AudienceScope(scope).label for scope in AudienceScope.values if scope in chosen]

    team_names = list(team_names)
    if len(team_names) == 1:
        parts.append(f"تیم {team_names[0]}")
    elif team_names:
        parts.append(f"{len(team_names)} تیم")

    usernames = list(usernames)
    if len(usernames) == 1:
        parts.append(usernames[0])
    elif usernames:
        parts.append(f"{len(usernames)} نفر")

    return "، ".join(parts) if parts else "بدون گیرنده"


def describe_audience(message: Message) -> str:
    """The same summary for a saved message, for the Sent list and the admin."""
    return describe_selection(
        scopes=message.scopes,
        team_names=message.teams.values_list("name", flat=True),
        usernames=message.users.values_list("username", flat=True),
    )


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
            {"title": message.title},
            recipients=user_ids,
        )

    logger.info(
        "Message %s (%s) sent to %d recipient(s)",
        message.pk,
        describe_audience(message),
        len(user_ids),
    )
    return len(user_ids)


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
