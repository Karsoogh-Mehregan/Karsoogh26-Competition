"""Why a duel was refused.

Service-level, not HTTP: `views._map_service_error` turns each of these into the
right status, the same way `minesweeper/views.py` does. Every message is the
Persian sentence a player reads, because every one of these is a refusal the
player caused and can fix.
"""


class DuelServiceError(Exception):
    """Base for everything this app refuses."""


class GameNotRunning(DuelServiceError):
    pass


class NotAdjacent(DuelServiceError):
    pass


class BuildingNotFull(DuelServiceError):
    pass


class InvalidTarget(DuelServiceError):
    pass


class AlreadyInDuel(DuelServiceError):
    """The team already has an open duel, as attacker or as defender."""


class OnCooldown(DuelServiceError):
    """Inside the rest window that follows every duel."""


class StakeUnaffordable(DuelServiceError):
    pass


class NoRoomAvailable(DuelServiceError):
    """Every judge is busy, or none has been given a room yet."""


class DuelClosed(DuelServiceError):
    pass
