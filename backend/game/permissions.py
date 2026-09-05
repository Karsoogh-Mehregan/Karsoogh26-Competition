from django.db.models import QuerySet
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


def question_visible_to_mentor(question, user) -> bool:
    """Whether this mentor may see or grade the question.

    Superusers see every question. Everyone else only sees questions
    assigned to them; unassigned questions stay off the mentor queue.
    """
    if getattr(user, "is_superuser", False):
        return True
    if question is None:
        return False
    return question.mentor_id == user.pk


def submissions_for_mentor(qs: QuerySet, user) -> QuerySet:
    """Submissions this mentor may list, open, or grade."""
    if getattr(user, "is_superuser", False):
        return qs
    return qs.filter(occupancy__question__mentor=user)
