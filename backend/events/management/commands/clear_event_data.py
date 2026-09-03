from django.core.management.base import BaseCommand
from django.db import transaction

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


class Command(BaseCommand):
    help = (
        "Delete event matches/history while preserving users, teams, balances, and configuration."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        total = 0
        for model in (
            MatchmakingTicket,
            TerritoryGame,
            CharityBagEvent,
            CentipedeGame,
            OlympicsMatch,
            AuctionEvent,
            WheelSpin,
            WheelEvent,
            PigGame,
            PigEvent,
        ):
            deleted, _ = model.objects.all().delete()
            total += deleted
        self.stdout.write(self.style.SUCCESS(f"Cleared {total} event records."))
