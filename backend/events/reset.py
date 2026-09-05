"""Clear the events app for a restart.

Every event instance is run state: a charity bag, an auction, a wheel and a pig
event were opened for *this* run, and a territory match, a centipede game, an
olympics match, a pig game, a wheel spin and a matchmaking ticket are things
teams did. `EventConfiguration` is the organiser's catalogue and stays.

Deletion order is not cosmetic. `PigGame.event` is a PROTECT foreign key onto
`PigEvent`, and `WheelSpin.prize` is a PROTECT onto a `WheelPrize` that hangs off
the event, so the owning rows have to go after the rows pointing at them or the
restart aborts with `ProtectedError`.

A whole-event restart also puts the primary keys back to 1, because organisers
read instances out loud as "نوبت ۲" and a second run that starts at 47 is
unreadable. A one-board restart leaves the sequences alone: the other contest's
rows are still there, so restarting the counter would collide with them.
"""

from django.core.management.color import no_style
from django.db import connection

from events.models import (
    AuctionEvent,
    CentipedeGame,
    CharityBagEvent,
    MatchmakingTicket,
    OlympicsMatch,
    PigEvent,
    PigGame,
    TerritoryGame,
    WheelEvent,
    WheelSpin,
)

_SEQUENCE_MODELS = (
    AuctionEvent,
    CentipedeGame,
    CharityBagEvent,
    MatchmakingTicket,
    OlympicsMatch,
    PigEvent,
    PigGame,
    TerritoryGame,
    WheelEvent,
    WheelSpin,
)


def _reset_sequences() -> None:
    sequences = [
        {"table": model._meta.db_table, "column": model._meta.pk.column}
        for model in _SEQUENCE_MODELS
    ]
    statements = connection.ops.sequence_reset_by_name_sql(no_style(), sequences)
    if not statements:
        return
    with connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


def clear_event_state(board: str | None = None) -> dict:
    """Delete every event instance and game, one board or both.

    Returns a count per model group so a restart can report what it removed.
    """

    def wipe(manager, field, label):
        rows = manager.all() if board is None else manager.filter(**{field: board})
        # delete() returns (total_across_all_models, per_model_counts); the total
        # would fold every cascaded cell, bid, roll and participation into the
        # instance count and make the restart summary unreadable.
        _total, counts = rows.delete()
        return counts.get(f"events.{label}", 0)

    tickets = wipe(MatchmakingTicket.objects, "team__board", "MatchmakingTicket")
    territory = wipe(TerritoryGame.objects, "player_one__board", "TerritoryGame")
    centipede = wipe(CentipedeGame.objects, "player_one__board", "CentipedeGame")
    olympics = wipe(OlympicsMatch.objects, "player_one__board", "OlympicsMatch")
    charity = wipe(CharityBagEvent.objects, "board", "CharityBagEvent")
    auctions = wipe(AuctionEvent.objects, "board", "AuctionEvent")
    wipe(WheelSpin.objects, "team__board", "WheelSpin")
    wheels = wipe(WheelEvent.objects, "board", "WheelEvent")
    pig_games = wipe(PigGame.objects, "team__board", "PigGame")
    pig_events = wipe(PigEvent.objects, "board", "PigEvent")

    if board is None:
        _reset_sequences()

    return {
        "matchmaking_tickets": tickets,
        "territory_games": territory,
        "centipede_games": centipede,
        "olympics_matches": olympics,
        "charity_bags": charity,
        "auctions": auctions,
        "wheel_events": wheels,
        "pig_games": pig_games,
        "pig_events": pig_events,
    }
