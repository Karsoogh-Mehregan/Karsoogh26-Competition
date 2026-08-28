from rest_framework.exceptions import APIException

from teams.models import Team

ACTING_TEAM_SESSION_KEY = "acting_team_id"


class NoActingTeam(APIException):
    status_code = 409
    default_detail = "No acting team selected."
    default_code = "no_acting_team"


def set_acting_team(request, team: Team) -> None:
    request.session[ACTING_TEAM_SESSION_KEY] = team.pk


def resolve_acting_team(request) -> Team:
    """Return the team this request acts as.

    Game endpoints must call this rather than reading the session key themselves.
    """
    team_id = request.session.get(ACTING_TEAM_SESSION_KEY)
    if team_id is not None:
        try:
            return Team.objects.get(pk=team_id)
        except Team.DoesNotExist:
            request.session.pop(ACTING_TEAM_SESSION_KEY, None)
            raise NoActingTeam
    team = getattr(request.user, "team", None)
    if team is not None:
        return team
    raise NoActingTeam
