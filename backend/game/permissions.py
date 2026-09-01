from rest_framework.permissions import BasePermission


class IsTeamMember(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.team_id)


class IsOwnTeam(BasePermission):
    """The `team_code` path segment must be the caller's own team."""

    message = "شما عضو این تیم نیستید."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.team_id):
            return False
        return view.kwargs.get("team_code") == user.team.code
