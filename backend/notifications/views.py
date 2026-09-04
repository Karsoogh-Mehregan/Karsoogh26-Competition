"""The inbox every user reads, and the composer only announcers may open."""

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.openapi import OpenApiExample, OpenApiParameter, extend_schema
from game.api_exceptions import Conflict
from teams.models import Team

from . import services
from .models import AudienceScope, Message, MessageStatus, Notification
from .permissions import CanSendAnnouncement
from .serializers import (
    AudienceOptionsSerializer,
    AudiencePreviewSerializer,
    AudienceSelectionSerializer,
    InboxItemSerializer,
    InboxSerializer,
    MarkReadSerializer,
    MessageRecipientsSerializer,
    MessageSerializer,
    MessageWriteSerializer,
    ReadResultSerializer,
    SendResultSerializer,
)

User = get_user_model()

# How many cards one inbox read returns. The contest runs a few hours; nobody
# accumulates a backlog worth paging through, and a cap beats a page cursor
# that the panel would have to manage.
DEFAULT_INBOX_LIMIT = 60
MAX_INBOX_LIMIT = 200

_INBOX_ITEM = {
    "id": 12,
    "title": "شروع مرحلهٔ دوم",
    "body": "تیم‌ها تا ده دقیقهٔ دیگر سر میزها حاضر باشند.",
    "excerpt": "تیم‌ها تا ده دقیقهٔ دیگر سر میزها حاضر باشند.",
    "sender": "داور اصلی",
    "sent_at": "2026-09-03T10:05:00+03:30",
    "created_at": "2026-09-03T10:05:00+03:30",
    "is_read": False,
    "read_at": None,
}

_MESSAGE = {
    "id": 4,
    "status": "sent",
    "title": "شروع مرحلهٔ دوم",
    "body": "تیم‌ها تا ده دقیقهٔ دیگر سر میزها حاضر باشند.",
    "excerpt": "تیم‌ها تا ده دقیقهٔ دیگر سر میزها حاضر باشند.",
    "scopes": ["teams"],
    "teams": [],
    "users": [],
    "audience_label": "همهٔ تیم‌ها",
    "sender": "داور اصلی",
    "created_at": "2026-09-03T09:58:00+03:30",
    "updated_at": "2026-09-03T10:00:00+03:30",
    "sent_at": "2026-09-03T10:00:00+03:30",
    "recipient_count": 48,
    "read_count": 31,
}


def _inbox_limit(request) -> int:
    raw = request.query_params.get("limit")
    if not raw:
        return DEFAULT_INBOX_LIMIT
    try:
        return max(1, min(MAX_INBOX_LIMIT, int(raw)))
    except ValueError:
        return DEFAULT_INBOX_LIMIT


@extend_schema(
    tags=["notifications"],
    summary="Read my inbox",
    description=(
        "Every notification addressed to the caller, newest first, with the unread "
        "count alongside. One call so the bell's dot and the list it opens can never "
        "disagree. `unread=true` narrows it to what is still unread."
    ),
    parameters=[
        OpenApiParameter("unread", str, OpenApiParameter.QUERY, enum=["true", "false"]),
        OpenApiParameter("limit", int, OpenApiParameter.QUERY, description="1–200, default 60"),
    ],
    responses=InboxSerializer,
    examples=[
        OpenApiExample(
            "inbox",
            value={"unread": 1, "total": 1, "results": [_INBOX_ITEM]},
            response_only=True,
        ),
    ],
)
class InboxView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InboxSerializer

    def get(self, request):
        unread_only = request.query_params.get("unread") == "true"
        rows = services.inbox(request.user, limit=_inbox_limit(request), unread_only=unread_only)
        return Response(
            InboxSerializer(
                {
                    "unread": services.unread_count(request.user),
                    "total": len(rows),
                    "results": rows,
                }
            ).data
        )


@extend_schema(
    tags=["notifications"],
    summary="Read one notification in full",
    description=(
        "One card from the caller's own inbox, for its detail page. Deliberately does "
        "not mark it read: a GET should not change state, so the page posts to "
        "`notifications/read/` once it has it."
    ),
    parameters=[OpenApiParameter("pk", int, OpenApiParameter.PATH)],
    responses=InboxItemSerializer,
    examples=[OpenApiExample("item", value=_INBOX_ITEM, response_only=True)],
)
class NotificationDetailView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = InboxItemSerializer

    def get(self, request, pk: int):
        notification = get_object_or_404(
            Notification.objects.for_user(request.user).select_related(
                "message", "message__sender"
            ),
            pk=pk,
        )
        return Response(InboxItemSerializer(notification).data)


@extend_schema(
    tags=["notifications"],
    summary="Mark notifications read",
    description=(
        "Marks the caller's own notifications read and returns the new unread count. "
        "Ids belonging to anyone else are ignored rather than refused, so a stale "
        "panel cannot 404 the whole call."
    ),
    request=MarkReadSerializer,
    responses=ReadResultSerializer,
    examples=[
        OpenApiExample("request", value={"ids": [12, 13]}, request_only=True),
        OpenApiExample("done", value={"marked": 2, "unread": 0}, response_only=True),
    ],
)
class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MarkReadSerializer

    def post(self, request):
        payload = MarkReadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        marked = services.mark_read(request.user, payload.validated_data["ids"])
        return Response({"marked": marked, "unread": services.unread_count(request.user)})


@extend_schema(
    tags=["notifications"],
    summary="Mark everything read",
    request=None,
    responses=ReadResultSerializer,
    examples=[OpenApiExample("done", value={"marked": 7, "unread": 0}, response_only=True)],
)
class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = None

    def post(self, request):
        marked = services.mark_all_read(request.user)
        return Response({"marked": marked, "unread": 0})


@extend_schema(
    tags=["notifications"],
    summary="Recipient picker options",
    description=(
        "The audiences that may be addressed, with their Persian labels, plus every "
        "team and every account that could be named individually."
    ),
    responses=AudienceOptionsSerializer,
)
class AudienceOptionsView(APIView):
    permission_classes = [CanSendAnnouncement]
    serializer_class = AudienceOptionsSerializer

    def get(self, request):
        return Response(
            AudienceOptionsSerializer(
                {
                    "choices": [
                        {"value": value, "label": label} for value, label in AudienceScope.choices
                    ],
                    "teams": Team.objects.order_by("name"),
                    "users": (
                        User.objects.filter(is_active=True)
                        .select_related("team")
                        .order_by("username")
                    ),
                }
            ).data
        )


@extend_schema(
    tags=["notifications"],
    summary="How many people a selection would reach",
    description=(
        "Counts the recipients of an audience without writing anything. The composer "
        "calls it as the picker changes, so an announcer can see that four teams means "
        "four people before committing. Excludes the caller, exactly as a real send does."
    ),
    request=AudienceSelectionSerializer,
    responses=AudiencePreviewSerializer,
    examples=[
        OpenApiExample(
            "request",
            value={"scopes": ["mentors"], "teams": ["alpha", "beta"], "users": []},
            request_only=True,
        ),
        OpenApiExample(
            "reach", value={"count": 11, "label": "همهٔ منتورها، ۲ تیم"}, response_only=True
        ),
    ],
)
class AudiencePreviewView(APIView):
    permission_classes = [CanSendAnnouncement]
    serializer_class = AudienceSelectionSerializer

    def post(self, request):
        payload = AudienceSelectionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        # An unsaved instance is enough: `recipients_for` only reads the three
        # selections and the sender, and building one avoids a throwaway row.
        preview = Message(scopes=data.get("scopes", []), sender=request.user)
        count, label = services.preview_audience(
            preview,
            teams=data.get("teams", []),
            users=data.get("users", []),
        )
        return Response({"count": count, "label": label})


class MessageViewBase(APIView):
    """Shared by the composer's endpoints. Announcers only, throughout."""

    permission_classes = [CanSendAnnouncement]

    def queryset(self, request):
        """Sent messages are the organisers' shared record; drafts are private.

        Two people editing one half-written announcement is a worse failure
        than not seeing a colleague's draft.

        Senderless messages are excluded: `duels.notices` writes those, several
        per duel, and they would bury the announcements this list exists to
        show. They are still delivered — this is the composer's record of what
        *people* wrote, not of every row in the table.
        """
        return (
            Message.objects.filter(
                Q(status=MessageStatus.SENT, sender__isnull=False) | Q(sender=request.user),
            )
            .select_related("sender")
            .prefetch_related("teams", "users")
            .annotate(
                delivered_count=Count("notifications", distinct=True),
                opened_count=Count(
                    "notifications",
                    filter=Q(notifications__read_at__isnull=False),
                    distinct=True,
                ),
            )
        )

    def sender_label(self, user) -> str:
        return user.get_full_name() or user.username


@extend_schema(
    tags=["notifications"],
    summary="List or compose messages",
    description=(
        "GET returns the announcer's drafts and every sent message, newest first; "
        "filter with `status`. POST saves a draft — it does not send. Use "
        "`messages/<id>/send/` for that, or POST with `send: true` to do both."
    ),
    parameters=[
        OpenApiParameter("status", str, OpenApiParameter.QUERY, enum=["draft", "sent"]),
    ],
    request=MessageWriteSerializer,
    responses=MessageSerializer,
    examples=[
        OpenApiExample(
            "request",
            value={"title": "شروع مرحلهٔ دوم", "body": "…", "audience": "teams"},
            request_only=True,
        ),
        OpenApiExample("row", value=_MESSAGE, response_only=True),
    ],
)
class MessageListView(MessageViewBase):
    serializer_class = MessageWriteSerializer

    def get(self, request):
        rows = self.queryset(request)
        wanted = request.query_params.get("status")
        if wanted in {MessageStatus.DRAFT, MessageStatus.SENT}:
            rows = rows.filter(status=wanted)
        return Response(MessageSerializer(rows, many=True).data)

    def post(self, request):
        payload = MessageWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        message = payload.save(
            sender=request.user,
            sender_label=self.sender_label(request.user),
            status=MessageStatus.DRAFT,
        )

        if request.data.get("send") is True:
            if not message.has_audience:
                raise Conflict("گیرنده‌ای انتخاب نشده است.")
            delivered = services.send_message(message)
            message.refresh_from_db()
            return Response(
                SendResultSerializer({"message": message, "delivered": delivered}).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["notifications"],
    summary="Read, edit or discard one message",
    description=(
        "PATCH and DELETE apply to drafts only: a sent message has already landed in "
        "other people's inboxes, so editing it would rewrite what they were told."
    ),
    parameters=[OpenApiParameter("pk", int, OpenApiParameter.PATH)],
    request=MessageWriteSerializer,
    responses=MessageSerializer,
    examples=[OpenApiExample("row", value=_MESSAGE, response_only=True)],
)
class MessageDetailView(MessageViewBase):
    serializer_class = MessageWriteSerializer

    def get_message(self, request, pk: int) -> Message:
        return get_object_or_404(self.queryset(request), pk=pk)

    def require_draft(self, message: Message) -> None:
        if message.status != MessageStatus.DRAFT:
            raise Conflict("این پیام ارسال شده و دیگر قابل ویرایش نیست.")

    def get(self, request, pk: int):
        return Response(MessageSerializer(self.get_message(request, pk)).data)

    def patch(self, request, pk: int):
        message = self.get_message(request, pk)
        self.require_draft(message)
        payload = MessageWriteSerializer(message, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        payload.save()
        message.refresh_from_db()
        return Response(MessageSerializer(message).data)

    def delete(self, request, pk: int):
        message = self.get_message(request, pk)
        self.require_draft(message)
        message.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["notifications"],
    summary="Who received a message, and who has opened it",
    description=(
        "Read receipts for one sent message, unread first — that is the question a "
        "sender actually has. A team account is labelled by its team name rather than "
        "its login, because that is who the sender is chasing."
    ),
    parameters=[OpenApiParameter("pk", int, OpenApiParameter.PATH)],
    responses=MessageRecipientsSerializer,
    examples=[
        OpenApiExample(
            "receipts",
            value={
                "delivered": 2,
                "read": 1,
                "unread": 1,
                "recipients": [
                    {
                        "id": 9,
                        "user_id": 5,
                        "username": "alborz",
                        "label": "البرز",
                        "team_code": "alborz",
                        "team_name": "البرز",
                        "is_read": False,
                        "read_at": None,
                    }
                ],
            },
            response_only=True,
        ),
    ],
)
class MessageRecipientsView(MessageViewBase):
    serializer_class = MessageRecipientsSerializer

    def get(self, request, pk: int):
        message = get_object_or_404(self.queryset(request), pk=pk)
        rows = list(
            message.notifications.select_related("user", "user__team").order_by(
                # nulls_first is explicit on purpose: Postgres and SQLite
                # disagree about where NULLs land by default, and "unread first"
                # is the whole point of the ordering.
                F("read_at").asc(nulls_first=True),
                "user__username",
            )
        )
        read = sum(1 for row in rows if row.read_at is not None)
        return Response(
            MessageRecipientsSerializer(
                {
                    "delivered": len(rows),
                    "read": read,
                    "unread": len(rows) - read,
                    "recipients": rows,
                }
            ).data
        )


@extend_schema(
    tags=["notifications"],
    summary="Send a draft",
    description=(
        "Fans the message out to its audience and returns how many people it reached. "
        "Sending an already-sent message is refused rather than duplicated."
    ),
    parameters=[OpenApiParameter("pk", int, OpenApiParameter.PATH)],
    request=None,
    responses=SendResultSerializer,
    examples=[
        OpenApiExample(
            "delivered",
            value={"message": _MESSAGE, "delivered": 48},
            response_only=True,
        ),
    ],
)
class MessageSendView(MessageViewBase):
    serializer_class = None

    def post(self, request, pk: int):
        message = get_object_or_404(self.queryset(request), pk=pk)
        if message.status == MessageStatus.SENT:
            raise Conflict("این پیام قبلاً ارسال شده است.")
        # Refused rather than sent to nobody: an empty audience would report
        # success and reach no one, which is the worst of both.
        if not message.has_audience:
            raise Conflict("گیرنده‌ای انتخاب نشده است.")

        delivered = services.send_message(message)
        message.refresh_from_db()
        return Response(SendResultSerializer({"message": message, "delivered": delivered}).data)


__all__ = [
    "AudienceOptionsView",
    "InboxView",
    "MarkAllReadView",
    "MarkReadView",
    "MessageDetailView",
    "MessageListView",
    "MessageRecipientsView",
    "MessageSendView",
    "NotificationDetailView",
]
