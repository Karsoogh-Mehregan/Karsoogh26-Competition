class GameServiceError(Exception):
    """Base for domain errors raised by game services."""


class NoQuestionAvailable(GameServiceError):
    """No unused active question remains in the level pool."""


class OccupancyNotActive(GameServiceError):
    """Occupancy is released or otherwise unavailable."""


class GameNotRunning(GameServiceError):
    """Game is not in the running state."""


class SubmissionWindowClosed(GameServiceError):
    """The answer window has expired."""


class AlreadySubmitted(GameServiceError):
    """This occupancy already has a submission."""


class NotTeamMember(GameServiceError):
    """The acting user does not belong to the occupancy's team."""


class InvalidAnswerPayload(GameServiceError):
    """Submission body/file does not match the question's answer_type."""


class AlreadyGraded(GameServiceError):
    """This occupancy has already been graded."""


class MissingFloor(GameServiceError):
    """Cannot grade before the occupancy floor is assigned."""


class NoEntryQuestions(GameServiceError):
    """The active entry pool is too small to fill a team's sheet."""


class NotOnEntrySheet(GameServiceError):
    """The team was never served this entry question."""


class EntryAlreadyAnswered(GameServiceError):
    """Entry questions are one shot; this one is already spent."""


class EntryNotAnswered(GameServiceError):
    """Only a question the team has already answered can be swapped."""


class EntryAnswerWasCorrect(GameServiceError):
    """A correct answer is not swappable; there is nothing to retry."""


class NoEntryRefreshesLeft(GameServiceError):
    """The team has spent its entry-question swaps."""
