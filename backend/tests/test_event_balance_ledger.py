from uuid import uuid4

import pytest

from core.boards import Board
from events.exceptions import CentipedeNotActive
from events.services import (
    create_auction_event,
    create_centipede_game,
    create_pig_event,
    play_centipede_action,
    play_pig_action,
    start_pig_game,
)
from teams.models import BalanceEvent, BalanceReason, Team

pytestmark = pytest.mark.django_db


def test_centipede_entries_and_payouts_are_logged_once():
    first = Team.objects.create(board=Board.GIRLS, code="first", name="First", balance=500)
    second = Team.objects.create(board=Board.GIRLS, code="second", name="Second", balance=500)
    game = create_centipede_game(first, second)
    play_centipede_action(game.pk, first, "steal", 1)
    play_centipede_action(game.pk, second, "preserve", 1)
    with pytest.raises(CentipedeNotActive):
        play_centipede_action(game.pk, second, "preserve", 1)
    assert list(
        BalanceEvent.objects.filter(team=first)
        .order_by("pk")
        .values_list("delta", "balance_after", "reason")
    ) == [(-100, 400, BalanceReason.EVENT), (160, 560, BalanceReason.EVENT)]
    assert list(
        BalanceEvent.objects.filter(team=second)
        .order_by("pk")
        .values_list("delta", "balance_after")
    ) == [(-100, 400), (40, 440)]


def test_pig_entry_and_payout_appear_in_wallet_history():
    team = Team.objects.create(board=Board.GIRLS, code="pig", name="Pig", balance=500)
    game = start_pig_game(create_pig_event(board=Board.GIRLS, max_pot=100).pk, team)
    play_pig_action(game.pk, team, "roll", uuid4(), roll_die=lambda: 6)
    request_id = uuid4()
    play_pig_action(game.pk, team, "cash_out", request_id)
    play_pig_action(game.pk, team, "cash_out", request_id)
    assert list(
        BalanceEvent.objects.filter(team=team).order_by("pk").values_list("delta", "balance_after")
    ) == [(-200, 300), (60, 360)]


def test_auction_automatic_award_is_logged():
    team = Team.objects.create(board=Board.GIRLS, code="solo", name="Solo", balance=500)
    event = create_auction_event(board=Board.GIRLS)
    entry = BalanceEvent.objects.get(team=team)
    assert entry.delta == event.reward
    assert entry.balance_after == 500 + event.reward
    assert entry.reason == BalanceReason.EVENT
