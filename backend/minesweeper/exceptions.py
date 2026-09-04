class MinesweeperServiceError(Exception):
    """Base for domain errors raised by minesweeper services."""


class InvalidDifficulty(MinesweeperServiceError):
    """difficulty is not one of the three configured layouts."""


class SettingsNotConfigured(MinesweeperServiceError):
    """The node has no MinesweeperSettings row."""


class SettingsDisabled(MinesweeperServiceError):
    """MinesweeperSettings.enabled is false."""


class EntryUnauthorized(MinesweeperServiceError):
    """No valid, unused, unexpired map-entry authorization for this node."""


class NodeUnreachable(MinesweeperServiceError):
    """The team cannot reach this Minesweeper node on the map.

    For a toll gate that means it holds nothing adjacent to the gate, and has no
    board of its own there to reopen.
    """


class GameFinished(MinesweeperServiceError):
    """The attempt is won or lost and no longer accepts moves."""


class InvalidCell(MinesweeperServiceError):
    """row/col is outside the board."""


class CellAlreadyRevealed(MinesweeperServiceError):
    """This cell has already been revealed."""


class CellFlagged(MinesweeperServiceError):
    """A flagged cell cannot be revealed."""


class CannotFlagRevealed(MinesweeperServiceError):
    """A revealed cell cannot be flagged or unflagged."""


class EntryFeeUnaffordable(MinesweeperServiceError):
    """The team cannot afford this node's entry cost."""
