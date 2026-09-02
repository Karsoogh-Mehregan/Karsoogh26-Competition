from rest_framework.permissions import BasePermission

from game.models import GameSettings

MENTOR_PERM = "game.act_as_mentor"
GAME_GOD_PERM = "game.control_game"


class IsMentor(BasePermission):
    """The single mentor check for the whole API.

    Backed by the `act_as_mentor` permission and the `Mentors` group that
    `game/migrations/0004_seed_mentor_group.py` seeds. Superusers pass implicitly.
    """

    message = "این عملیات فقط برای منتورها مجاز است."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm(MENTOR_PERM))


class IsGameGod(BasePermission):
    """Whoever may drive the event itself: start, pause, restart, reconfigure.

    Deliberately not implied by IsMentor. Mentors are many and they grade;
    the game god is the handful of people allowed to touch the run itself, so
    a mistaken click cannot wipe the board mid-contest. Backed by the
    `control_game` permission and the `GameGods` group seeded in
    `game/migrations/0010_game_god_group.py`. Superusers pass implicitly.
    """

    message = "این عملیات فقط برای گردانندهٔ بازی مجاز است."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm(GAME_GOD_PERM))


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
