from rest_framework.permissions import SAFE_METHODS, BasePermission

from accounts.permissions import MENTOR_PERM


class IsTerritoryParticipant(BasePermission):
    """Players may read and move; mentors may only read a match."""

    message = "شما به این مسابقه دسترسی ندارید."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in SAFE_METHODS and user.has_perm(MENTOR_PERM):
            return True
        return user.team_id in (obj.player_one_id, obj.player_two_id)
