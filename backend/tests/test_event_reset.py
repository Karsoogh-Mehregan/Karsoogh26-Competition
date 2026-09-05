from datetime import timedelta

import pytest
from django.utils import timezone

from core.boards import Board
from events.models import CharityBagEvent, CharityBagSide, PigEvent, PigGame, PigGameStatus
from events.services import create_charity_bag, enter_charity_bag
from game.services import restart_game
from teams.models import Team

pytestmark = pytest.mark.django_db


def _teams():
    return (
        Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=100),
        Team.objects.create(board=Board.BOYS, code="bravo", name="Bravo", balance=100),
    )


def _charity(board):
    now = timezone.now()
    return create_charity_bag(now - timedelta(seconds=5), now + timedelta(minutes=10), board=board)


def test_restart_clears_event_instances_and_restarts_the_numbering():
    girls, _boys = _teams()
    event = _charity(Board.GIRLS)
    enter_charity_bag(event.pk, girls, CharityBagSide.MICE, 20)
    pig_event = PigEvent.objects.create(board=Board.GIRLS, max_pot=500)
    PigGame.objects.create(
        event=pig_event,
        team=girls,
        entry_fee=pig_event.entry_fee,
        max_pot=pig_event.max_pot,
        status=PigGameStatus.ACTIVE,
    )

    summary = restart_game()

    assert summary["charity_bags"] == 1
    assert summary["pig_events"] == summary["pig_games"] == 1
    assert not CharityBagEvent.objects.exists()
    assert not PigEvent.objects.exists()

    assert _charity(Board.GIRLS).pk == 1


def test_a_one_board_restart_leaves_the_other_contest_playing():
    girls, boys = _teams()
    girls_event = _charity(Board.GIRLS)
    boys_event = _charity(Board.BOYS)
    enter_charity_bag(girls_event.pk, girls, CharityBagSide.MICE, 20)
    enter_charity_bag(boys_event.pk, boys, CharityBagSide.LIONS, 20)

    restart_game(board=Board.GIRLS)

    assert list(CharityBagEvent.objects.values_list("pk", flat=True)) == [boys_event.pk]
    # The other board still owns its ids, so the counter must not restart under it.
    assert _charity(Board.GIRLS).pk > boys_event.pk
