from rest_framework.permissions import BasePermission

from game.models import GameSettings

MENTOR_PERM = "game.act_as_mentor"


class IsMentor(BasePermission):
    """The single mentor check for the whole API.

    Backed by the `act_as_mentor` permission and the `Mentors` group that
    `game/migrations/0004_seed_mentor_group.py` seeds. Superusers pass implicitly.
    """

    message = "این عملیات فقط برای منتورها مجاز است."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm(MENTOR_PERM))


class GameIsRunning(BasePermission):
    """Reject game actions unless GameSettings.status is RUNNING."""

    message = "The game is not running."

    def has_permission(self, request, view):
        return GameSettings.load().is_running


class CanViewLeaderboard(BasePermission):
    """Mentors always see the leaderboard; teams only once it is made public."""

    message = "جدول امتیازات پنهان است."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.has_perm(MENTOR_PERM):
            return True
        return GameSettings.load().leaderboard_public
