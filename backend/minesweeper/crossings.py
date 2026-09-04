"""Which toll gates a team has already cleared.

A toll node is a gate in the road, not a building: it has no floors, no
networth and no capacity, and any number of teams may stand on it. So a
crossing is not an `Occupancy` — it is simply a won attempt on a toll node,
which is the only record the game needs and the only one it can never
contradict. `game.services.movement` reads this to open the one-way edges that
leave the gate.
"""

from game.models import Level, Node
from minesweeper.models import MinesweeperAttempt, MinesweeperStatus
from teams.models import Team


def _won_toll_attempts():
    return MinesweeperAttempt.objects.filter(
        status=MinesweeperStatus.WON,
        game__node__level_id=Level.TOLL,
    )


def is_toll(node: Node) -> bool:
    return node.level_id == Level.TOLL


def cleared_node_ids(team: Team) -> set[int]:
    """Primary keys of the toll nodes this team has beaten."""
    return set(_won_toll_attempts().filter(team=team).values_list("game__node_id", flat=True))


def cleared_node_codes(team: Team) -> list[str]:
    codes = _won_toll_attempts().filter(team=team).values_list("game__node__code", flat=True)
    return sorted(set(codes))


def has_cleared(team: Team, node: Node) -> bool:
    return _won_toll_attempts().filter(team=team, game__node_id=node.pk).exists()


def cleared_codes_by_team() -> dict[int, list[str]]:
    """Every team's cleared gates in one query, for the board snapshot."""
    by_team: dict[int, set[str]] = {}
    rows = _won_toll_attempts().values_list("team_id", "game__node__code")
    for team_id, code in rows:
        by_team.setdefault(team_id, set()).add(code)
    return {team_id: sorted(codes) for team_id, codes in by_team.items()}
