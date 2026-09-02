class MinesweeperServiceError(Exception):
    """Base for domain errors raised by minesweeper services."""


class InvalidDifficulty(MinesweeperServiceError):
    """difficulty is not one of the three configured layouts."""


class GameFinished(MinesweeperServiceError):
    """The game is won or lost and no longer accepts moves."""


class InvalidCell(MinesweeperServiceError):
    """row/col is outside the board."""


class CellAlreadyRevealed(MinesweeperServiceError):
    """This cell has already been revealed."""


class CellFlagged(MinesweeperServiceError):
    """A flagged cell cannot be revealed."""
