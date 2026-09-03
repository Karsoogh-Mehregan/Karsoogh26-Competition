from rest_framework.permissions import BasePermission

SEND_PERM = "notifications.send_announcement"


class CanSendAnnouncement(BasePermission):
    """Who may write into other people's inboxes.

    Its own permission rather than a reuse of `act_as_mentor` or `control_game`:
    announcing is neither grading nor running the clock, and an organiser may
    well want to hand it to someone who does neither.
    `notifications/migrations/0002` seeds it onto the existing GameGods group,
    so the people already running the event have it on day one; anyone else is
    one checkbox away in the Django admin.

    Superusers pass implicitly, as with `IsMentor`. Unlike `IsGameGod` there is
    nothing destructive behind this gate — the worst a stray click does is send
    a message.
    """

    message = "اجازهٔ ارسال پیام ندارید."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm(SEND_PERM))
