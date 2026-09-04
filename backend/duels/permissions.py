from rest_framework.permissions import BasePermission

JUDGE_PERM = "duels.judge_duel"


class IsDuelMentor(BasePermission):
    """Who may call a winner.

    Its own permission, backed by the **DuelMentors** group seeded in
    `duels/migrations/0002`. A duel judge runs a meeting and reports a result;
    that is neither grading (`act_as_mentor`) nor running the event
    (`control_game`), and an organiser hands it out separately. Someone doing
    both jobs goes in both groups.

    Holding the permission is not enough to close a *particular* duel — the view
    also checks that the caller is the judge the queue assigned to it.
    """

    message = "این عملیات فقط برای داوران دوئل مجاز است."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.has_perm(JUDGE_PERM))
