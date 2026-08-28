from rest_framework.permissions import BasePermission

MENTOR_PERM = "game.act_as_mentor"


class IsMentor(BasePermission):
    message = "این عملیات فقط برای منتورها مجاز است."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm(MENTOR_PERM))
