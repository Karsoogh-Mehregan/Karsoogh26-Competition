from rest_framework.permissions import BasePermission

SEND_PERM = "notifications.send_announcement"


class CanSendAnnouncement(BasePermission):
    """Who may write into other people's inboxes.

    Its own permission rather than a reuse of `act_as_mentor` or `control_game`:
    announcing is neither grading nor running the clock. It is backed by the
    **Notifier** group, seeded in `notifications/migrations/0003`; running the
    event and speaking to the hall are different jobs, held by different people
    on the day, so a game god who should also announce goes in both groups.

    Superusers pass implicitly, as with `IsMentor`. Unlike `IsGameGod` there is
    nothing destructive behind this gate — the worst a stray click does is send
    a message.
    """

    message = "اجازهٔ ارسال پیام ندارید."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm(SEND_PERM))
