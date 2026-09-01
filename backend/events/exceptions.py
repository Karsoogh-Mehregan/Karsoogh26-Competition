class TerritoryEventError(Exception):
    """Base class for territory-control domain errors."""


class SamePlayer(TerritoryEventError):
    """A two-player game requires two different teams."""


class NotParticipant(TerritoryEventError):
    """The acting team is not one of this game's players."""


class GameAlreadyFinished(TerritoryEventError):
    """No more turns can be played after the twentieth turn."""


class NotPlayersTurn(TerritoryEventError):
    """The acting team is not the active player."""


class InvalidStartingCell(TerritoryEventError):
    """A starting position must be an unowned boundary cell."""


class InvalidTarget(TerritoryEventError):
    """A normal move must target an adjacent neutral or enemy cell."""
