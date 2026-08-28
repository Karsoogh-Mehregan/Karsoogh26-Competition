from rest_framework.permissions import BasePermission


class IsTeamMember(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.team_id)
