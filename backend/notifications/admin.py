from django.contrib import admin, messages

from .models import Message, MessageStatus, Notification
from .services import describe_audience, send_message


class NotificationInline(admin.TabularInline):
    model = Notification
    extra = 0
    can_delete = False
    fields = ("user", "read_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "status",
        "audience",
        "sender_label",
        "delivered",
        "opened",
        "created_at",
        "sent_at",
    )
    list_filter = ("status",)
    search_fields = ("title", "body", "sender_label")
    list_select_related = ("sender",)
    autocomplete_fields = ("sender",)
    filter_horizontal = ("teams", "users")
    readonly_fields = ("created_at", "updated_at", "sent_at", "status")
    inlines = [NotificationInline]
    actions = ["send_now"]

    @admin.display(description="audience")
    def audience(self, message: Message) -> str:
        return describe_audience(message)

    @admin.display(description="delivered")
    def delivered(self, message: Message) -> int:
        return message.notifications.count()

    @admin.display(description="read")
    def opened(self, message: Message) -> int:
        return message.notifications.filter(read_at__isnull=False).count()

    @admin.action(description="Send the selected drafts")
    def send_now(self, request, queryset):
        """The admin fallback for the composer in the SPA.

        Skips anything already sent rather than delivering it twice — the
        selection is a checkbox, and a double-send cannot be taken back.
        """
        sent = 0
        for message in queryset.filter(status=MessageStatus.DRAFT):
            send_message(message)
            sent += 1
        self.message_user(request, f"{sent} draft(s) sent.", messages.SUCCESS)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("message", "user", "read_at", "created_at")
    list_filter = ("read_at",)
    list_select_related = ("message", "user")
    search_fields = ("message__title", "user__username")
    autocomplete_fields = ("message", "user")

    def has_add_permission(self, request):
        # Delivery is the fan-out's job; a hand-made row would have no message
        # anyone else received.
        return False
