from rest_framework.permissions import BasePermission

from game.models import GameSettings

MENTOR_PERM = "game.act_as_mentor"
GAME_GOD_PERM = "game.control_game"
DESIGNER_PERM = "game.design_map"
# A plain string, not an import from `duels`: that app imports `accounts`.
DUEL_MENTOR_PERM = "duels.judge_duel"


class IsMentor(BasePermission):
    """The single mentor check for the whole API.

    Backed by the `act_as_mentor` permission and the `Mentors` group that
    `game/migrations/0004_seed_mentor_group.py` seeds. Superusers pass implicitly.
    """

    message = "این عملیات فقط برای منتورها مجاز است."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm(MENTOR_PERM))


def has_game_god_rights(user) -> bool:
    """Membership of GameGods, or the permission granted by hand.

    Deliberately *not* `user.has_perm()`: that returns True for every
    superuser, and the whole point of this group is that being a Django admin
    is not the same as being allowed to run the event. Someone has to be put
    in the group on purpose.
    """
    if not user or not user.is_authenticated:
        return False

    app_label, codename = GAME_GOD_PERM.split(".")
    return (
        user.groups.filter(
            permissions__codename=codename,
            permissions__content_type__app_label=app_label,
        ).exists()
        or user.user_permissions.filter(
            codename=codename, content_type__app_label=app_label
        ).exists()
    )


class IsGameGod(BasePermission):
    """Whoever may drive the event itself: start, pause, restart, reconfigure.

    Not implied by IsMentor and not implied by superuser. Mentors are many and
    they grade; the game god is the handful of people trusted with the run
    itself, so a mistaken click cannot wipe the board mid-contest. Backed by
    the `control_game` permission and the `GameGods` group seeded in
    `game/migrations/0011_game_god_group.py`.
    """

    message = "این عملیات فقط برای گروه GameGods مجاز است."

    def has_permission(self, request, view):
        return has_game_god_rights(request.user)


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


class IsDesigner(BasePermission):
    """May change how the map looks: building types, neighbourhood colours, roads.

    Backed by the `design_map` permission and the `Designers` group seeded in
    `game/migrations/0017_seed_map_design.py`. Deliberately cannot touch
    holdings, balances or the clock — a stray click in the design page must not
    be able to affect the standings.
    """

    message = "این عملیات فقط برای طراحان مجاز است."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm(DESIGNER_PERM))
