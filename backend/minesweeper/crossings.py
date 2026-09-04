"""Which toll gates a team has cleared, and which it still has open.

A toll node is a gate in the road, not a building: it has no floors, no
networth and no capacity, and any number of teams may stand on it. So a
crossing is not an `Occupancy` — it is simply a won attempt on a toll node,
which is the only record the game needs and the only one it can never
contradict. `game.services.movement` reads this to open the one-way edges that
leave the gate.

An *open* board is the other half the board needs to know about: the team has
already paid for it, so returning to that gate resumes rather than buys, and the
map must offer «ادامه بازی» instead of quoting the toll a second time.
"""

from game.models import Level, Node
from minesweeper.models import MinesweeperAttempt, MinesweeperStatus
from teams.models import Team


def _toll_attempts(status: str):
    return MinesweeperAttempt.objects.filter(
        status=status,
        game__node__level_id=Level.TOLL,
    )


def _won_toll_attempts():
    return _toll_attempts(MinesweeperStatus.WON)


def _open_toll_attempts():
    return _toll_attempts(MinesweeperStatus.IN_PROGRESS)


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


def open_board_node_codes(team: Team) -> list[str]:
    """Gates where this team has an unfinished board — paid for, resumable."""
    codes = _open_toll_attempts().filter(team=team).values_list("game__node__code", flat=True)
    return sorted(set(codes))
