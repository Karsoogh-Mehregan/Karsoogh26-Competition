class MinesweeperServiceError(Exception):
    """Base for domain errors raised by minesweeper services."""


class InvalidDifficulty(MinesweeperServiceError):
    """difficulty is not one of the three configured layouts."""
