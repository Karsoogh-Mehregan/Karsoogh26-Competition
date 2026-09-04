"""Wipe a run so the board can be played again.

Only ever reached through `IsGameGod` plus an explicit confirmation, because it
throws away every move of a contest. It resets *state*, never *content*: nodes,
edges, questions, the economy tables, the Minesweeper difficulties and the duel
rooms all survive, so the next run starts on the same map, with the same
question bank, judged by the same people.

The line between the two is the thing to get right when a new app lands. Anything
a *team* did is state and goes; anything an *organiser* configured is content and
stays. A duel room is content — an organiser typed its Skyroom link and picked
its judge — but the rotation cursor on it is state, so the room survives with its
place in the queue cleared.

One board or both. The two contests share a clock, so restarting one of them
clears its teams' state and deliberately leaves the ledger alone — there is no
per-board clock to zero. Passing no board keeps the whole-event behaviour,
clock included.
"""

import logging

from django.db import transaction

from duels.models import Duel, Room
from game.models import EntryAttempt, GameSettings, GameStatus, Occupancy
from minesweeper.models import MinesweeperGame
from notifications.models import Message, MessageStatus
from teams.models import BalanceEvent, Team

logger = logging.getLogger("karsoogh")


@transaction.atomic
def restart_game(*, by=None, board: str | None = None) -> dict:
    """Clear the board, refund every team, and put the game back to not-started.

    `board` narrows every delete to one contest and leaves the run ledger alone;
    None clears both and resets the clock.

    Returns what it removed, so the caller can report it honestly instead of a
    bare "done".
    """
    settings_row = GameSettings.load()
    teams_qs = Team.objects.all() if board is None else Team.objects.filter(board=board)

    def by_team(manager, field="team"):
        return manager.all() if board is None else manager.filter(**{f"{field}__board": board})

    # Duels go first, and not merely for tidiness: `Duel.target` is a PROTECT
    # foreign key onto Occupancy, so a single played duel makes the delete below
    # raise ProtectedError and takes the whole restart with it.
    duels, _ = by_team(Duel.objects, "attacker").delete()

    # The rooms themselves are content and stay. `last_assigned_at` is the
    # circular queue's cursor, though, so clearing it puts every judge back at
    # the front of the line instead of carrying last run's order into this one.
    # Rooms are shared by both contests, so their cursor is only cleared on a
    # whole-event restart; a one-board restart must not reshuffle the other's
    # judge queue.
    rooms = Room.objects.update(last_assigned_at=None) if board is None else 0

    # Submissions and TeamQuestions hang off Occupancy with CASCADE, so one
    # delete takes all three. Questions themselves are content and stay.
    # delete() returns (total_across_all_models, per_model_counts) — report the
    # per-model numbers, or "occupancies" silently includes the cascade.
    _total, deleted = by_team(Occupancy.objects).delete()

    # Toll crossings hang off Team and MinesweeperGame, never off Occupancy, so
    # the cascade above cannot reach them. Left behind, every team would start
    # the new run still holding the gates it paid for last time — and, because a
    # crossing is what opens the one-way roads out of a `C34`/`C45`, standing on
    # the outer rings for free. Deleting the generated boards takes their
    # attempts with them (CASCADE) and makes the next team face a fresh mine
    # layout rather than one it has already solved. `MinesweeperSettings` — which
    # node has a board and at what difficulty — is configuration and stays.
    # Boards hang off a node, and nodes carry the board, so this narrows by
    # node rather than by team.
    minesweeper_games = MinesweeperGame.objects.all()
    if board is not None:
        minesweeper_games = minesweeper_games.filter(node__board=board)
    _boards, board_counts = minesweeper_games.delete()

    # The sheet hangs off Team, not Occupancy, so the cascade above misses it.
    # Left behind, last run's correct answers would clear the gate again and no
    # team would ever see a sheet. The EntryQuestion bank is content and stays.
    entry_attempts, _ = by_team(EntryAttempt.objects).delete()

    # The score log is run state, not content. Left behind, last contest's
    # credits and charges would still show in the team panel.
    balance_events, _ = by_team(BalanceEvent.objects).delete()

    # Sent mail is of this run; drafts are the announcer's unfinished work and
    # survive. Notifications cascade off Message, so inboxes empty with the
    # sent rows.
    # A message has no board — it is addressed, not owned — so only a whole-event
    # restart empties the hall's inboxes.
    if board is None:
        _total_mail, deleted_mail = Message.objects.filter(status=MessageStatus.SENT).delete()
    else:
        deleted_mail = {}

    teams = teams_qs.update(
        balance=settings_row.initial_balance,
        color=None,
        draft_order=None,
        last_duel_at=None,
    )

    # Zero the run ledger so both timers start over. `duration_minutes` is left
    # alone: an organiser set it deliberately, and it is the length of the game,
    # not a fact about the run that just ended.
    if board is None:
        settings_row.status = GameStatus.NOT_STARTED
        settings_row.started_at = None
        settings_row.accumulated_seconds = 0
        settings_row.running_since = None
        settings_row.save(
            update_fields=["status", "started_at", "accumulated_seconds", "running_since"]
        )

    summary = {
        "board": board or "all",
        "occupancies": deleted.get("game.Occupancy", 0),
        "submissions": deleted.get("game.Submission", 0),
        "entry_attempts": entry_attempts,
        "balance_events": balance_events,
        "sent_messages": deleted_mail.get("notifications.Message", 0),
        "duels": duels,
        "rooms_requeued": rooms,
        "minesweeper_attempts": board_counts.get("minesweeper.MinesweeperAttempt", 0),
        "minesweeper_boards": board_counts.get("minesweeper.MinesweeperGame", 0),
        "teams": teams,
    }
    logger.warning("Game restarted by %s: %s", getattr(by, "username", "unknown"), summary)
    return summary
