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


class NodeUnreachable(MinesweeperServiceError):
    """The team holds nothing adjacent to this gate, so it cannot enter yet."""


class AlreadyCleared(MinesweeperServiceError):
    """The team has already beaten this gate; there is nothing left to pay for."""


class EntryFeeUnaffordable(MinesweeperServiceError):
    """The team cannot afford this node's entry cost."""
