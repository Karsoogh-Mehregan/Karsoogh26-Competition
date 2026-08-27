from rest_framework.permissions import BasePermission

from game.models import GameSettings


class IsMentor(BasePermission):
    """Named seam for mentor-only views.

    Today this is any authenticated user; tighten here rather than at call sites.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class GameIsRunning(BasePermission):
    """Reject game actions unless GameSettings.status is RUNNING."""

    message = "The game is not running."

    def has_permission(self, request, view):
        return GameSettings.load().is_running
