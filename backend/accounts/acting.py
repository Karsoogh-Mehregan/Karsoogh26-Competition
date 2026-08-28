from rest_framework.exceptions import APIException

from teams.models import Team

ACTING_TEAM_SESSION_KEY = "acting_team_id"


class NoActingTeam(APIException):
    status_code = 409
    default_detail = "No acting team selected."
    default_code = "no_acting_team"


def set_acting_team(request, team: Team) -> None:
    request.session[ACTING_TEAM_SESSION_KEY] = team.pk


def clear_acting_team(request) -> None:
    """Explicitly drop the acting team; do not fall back to ``user.team``."""
    request.session[ACTING_TEAM_SESSION_KEY] = None


def resolve_acting_team(request) -> Team:
    """Return the team this request acts as.

    Game endpoints must call this rather than reading the session key themselves.
    """
    if ACTING_TEAM_SESSION_KEY in request.session:
        team_id = request.session[ACTING_TEAM_SESSION_KEY]
        if team_id is None:
            raise NoActingTeam
        try:
            return Team.objects.get(pk=team_id)
        except Team.DoesNotExist:
            request.session.pop(ACTING_TEAM_SESSION_KEY, None)
            raise NoActingTeam
    team = getattr(request.user, "team", None)
    if team is not None:
        return team
    raise NoActingTeam
