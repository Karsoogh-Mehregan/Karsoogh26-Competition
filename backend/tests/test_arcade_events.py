from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from events.exceptions import AuctionError, PigError, WheelError
from events.models import (
    AuctionBid,
    AuctionStatus,
    PigGameStatus,
    WheelDeliveryStatus,
    WheelStatus,
)
from events.services import (
    create_auction_event,
    create_pig_event,
    create_wheel_event,
    deliver_wheel_prize,
    place_auction_bid,
    play_pig_action,
    settle_auction_event,
    spin_wheel,
    start_pig_game,
    start_wheel_event,
)
from teams.models import Team

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def teams():
    return [
        Team.objects.create(code="alpha", name="Alpha", balance=500),
        Team.objects.create(code="beta", name="Beta", balance=400),
        Team.objects.create(code="gamma", name="Gamma", balance=300),
    ]


@pytest.fixture
def mentor():
    user = User.objects.create_user("mentor", password="secret")
    user.groups.add(Group.objects.get(name="Mentors"))
    return user


@pytest.fixture
def wheel_prizes():
    return [
        {
            "code": "coins",
            "prize_type": "glorium",
            "display_name": "20 Glorium",
            "glorium_amount": 20,
            "weight": 5,
        },
        {
            "code": "sticker",
            "prize_type": "merchandise",
            "display_name": "Sticker",
            "weight": 2,
            "stock": 1,
        },
        {
            "code": "grand",
            "prize_type": "grand_prize",
            "display_name": "Grand",
            "weight": 1,
        },
    ]


def test_auction_snapshots_ranking_pairs_and_automatic_odd_award(teams):
    event = create_auction_event(now=timezone.now())

    pairs = list(event.pairs.all())
    assert event.status == AuctionStatus.ACTIVE
    assert [(row["rank"], row["code"]) for row in event.ranking_snapshot] == [
        (1, "alpha"),
        (2, "beta"),
        (3, "gamma"),
    ]
    assert pairs[0].team_one == teams[0]
    assert pairs[0].team_two == teams[1]
    assert pairs[1].automatic_award is True
    assert pairs[1].winner == teams[2]
    assert Team.objects.get(pk=teams[2].pk).balance == 1300


def test_auction_bid_commits_only_increment_and_serializes_highest(teams):
    event = create_auction_event(now=timezone.now())
    pair = event.pairs.get(automatic_award=False)

    place_auction_bid(pair.pk, teams[0], 100, uuid4())
    place_auction_bid(pair.pk, teams[1], 120, uuid4())
    place_auction_bid(pair.pk, teams[0], 150, uuid4())

    pair.refresh_from_db()
    assert pair.team_one_bid == 150
    assert pair.team_two_bid == 120
    assert pair.highest_bidder == teams[0]
    assert Team.objects.get(pk=teams[0].pk).balance == 350
    assert Team.objects.get(pk=teams[1].pk).balance == 280
    assert list(AuctionBid.objects.values_list("committed_delta", flat=True)) == [100, 120, 50]
    with pytest.raises(AuctionError):
        place_auction_bid(pair.pk, teams[1], 150, uuid4())


def test_auction_settlement_is_idempotent_and_both_bids_stay_paid(teams):
    event = create_auction_event(now=timezone.now())
    pair = event.pairs.get(automatic_award=False)
    place_auction_bid(pair.pk, teams[0], 100, uuid4())
    place_auction_bid(pair.pk, teams[1], 120, uuid4())

    settle_auction_event(event.pk, now=event.ends_at)
    settle_auction_event(event.pk, now=event.ends_at)

    pair.refresh_from_db()
    assert pair.winner == teams[1]
    assert Team.objects.get(pk=teams[0].pk).balance == 400
    assert Team.objects.get(pk=teams[1].pk).balance == 1280


def test_auction_bid_retry_does_not_charge_twice(teams):
    event = create_auction_event(now=timezone.now())
    pair = event.pairs.get(automatic_award=False)
    request_id = uuid4()
    place_auction_bid(pair.pk, teams[0], 50, request_id)
    place_auction_bid(pair.pk, teams[0], 50, request_id)
    assert Team.objects.get(pk=teams[0].pk).balance == 450
    assert pair.bids.count() == 1


def test_wheel_glorium_spin_is_atomic_and_retry_safe(teams, wheel_prizes):
    event = create_wheel_event(prizes=wheel_prizes)
    start_wheel_event(event.pk)
    request_id = uuid4()

    first = spin_wheel(event.pk, teams[0], request_id, randbelow=lambda _: 0)
    second = spin_wheel(event.pk, teams[0], request_id, randbelow=lambda _: 7)

    event.refresh_from_db()
    assert first.pk == second.pk
    assert first.glorium_payout == 20
    assert Team.objects.get(pk=teams[0].pk).balance == 510
    assert event.total_collected == 10


def test_wheel_merchandise_stock_and_delivery(teams, wheel_prizes):
    event = create_wheel_event(prizes=wheel_prizes)
    start_wheel_event(event.pk)
    spin = spin_wheel(event.pk, teams[0], uuid4(), randbelow=lambda _: 5)

    spin.prize.refresh_from_db()
    assert spin.delivery_status == WheelDeliveryStatus.PENDING
    assert spin.prize.stock == 0
    assert spin.prize.available is False
    delivered = deliver_wheel_prize(spin.pk)
    assert delivered.delivery_status == WheelDeliveryStatus.DELIVERED
    assert deliver_wheel_prize(spin.pk).pk == spin.pk


def test_grand_prize_closes_wheel_and_cannot_be_claimed_twice(teams, wheel_prizes):
    event = create_wheel_event(prizes=wheel_prizes)
    start_wheel_event(event.pk)
    spin_wheel(event.pk, teams[0], uuid4(), randbelow=lambda _: 7)

    event.refresh_from_db()
    assert event.status == WheelStatus.GRAND_PRIZE_CLAIMED
    assert event.grand_prize_winner == teams[0]
    with pytest.raises(WheelError):
        spin_wheel(event.pk, teams[1], uuid4(), randbelow=lambda _: 0)


def test_wheel_requires_exactly_one_grand_prize(wheel_prizes):
    with pytest.raises(WheelError):
        create_wheel_event(prizes=wheel_prizes[:-1])


def test_pig_entry_roll_cashout_and_retry(teams):
    event = create_pig_event(max_pot=500)
    game = start_pig_game(event.pk, teams[0])
    roll_id = uuid4()
    play_pig_action(game.pk, teams[0], "roll", roll_id, roll_die=lambda: 4)
    play_pig_action(game.pk, teams[0], "roll", roll_id, roll_die=lambda: 6)
    cash_id = uuid4()
    play_pig_action(game.pk, teams[0], "cash_out", cash_id)
    play_pig_action(game.pk, teams[0], "cash_out", cash_id)

    game.refresh_from_db()
    assert game.pot == 40
    assert game.final_payout == 40
    assert game.status == PigGameStatus.FINISHED_CASHED_OUT
    assert Team.objects.get(pk=teams[0].pk).balance == 340
    assert game.rolls.count() == 1


def test_pig_rolled_one_loses_pot_and_finishes(teams):
    event = create_pig_event(max_pot=500)
    game = start_pig_game(event.pk, teams[0])
    play_pig_action(game.pk, teams[0], "roll", uuid4(), roll_die=lambda: 6)
    play_pig_action(game.pk, teams[0], "roll", uuid4(), roll_die=lambda: 1)

    game.refresh_from_db()
    assert game.pot == 0
    assert game.final_payout == 0
    assert game.status == PigGameStatus.FINISHED_ROLLED_ONE
    assert Team.objects.get(pk=teams[0].pk).balance == 300


def test_pig_caps_and_automatically_pays_max_pot(teams):
    event = create_pig_event(max_pot=50)
    game = start_pig_game(event.pk, teams[0])
    play_pig_action(game.pk, teams[0], "roll", uuid4(), roll_die=lambda: 6)

    game.refresh_from_db()
    assert game.pot == 50
    assert game.final_payout == 50
    assert game.status == PigGameStatus.FINISHED_MAX_POT
    assert Team.objects.get(pk=teams[0].pk).balance == 350


def test_pig_rejects_cashout_at_zero_and_insufficient_entry(teams):
    event = create_pig_event(max_pot=500)
    game = start_pig_game(event.pk, teams[0])
    with pytest.raises(PigError):
        play_pig_action(game.pk, teams[0], "cash_out", uuid4())
    poor = Team.objects.create(code="poor", name="Poor", balance=199)
    with pytest.raises(PigError):
        start_pig_game(event.pk, poor)


def test_api_permissions_keep_operator_and_team_actions_separate(
    client, teams, mentor, wheel_prizes
):
    client.force_login(mentor)
    wheel = client.post(
        "/api/events/prize-wheel/events/",
        {"spin_cost": 10, "prizes": wheel_prizes},
        content_type="application/json",
    )
    assert wheel.status_code == 201
    wheel_id = wheel.json()["id"]
    assert client.post(f"/api/events/prize-wheel/events/{wheel_id}/start/").status_code == 200

    player = User.objects.create_user("alpha", password="secret", team=teams[0])
    client.force_login(player)
    assert (
        client.post(
            f"/api/events/prize-wheel/events/{wheel_id}/spins/",
            {"request_id": str(uuid4())},
            content_type="application/json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/events/limited-auction/events/",
            {"duration_seconds": 600},
            content_type="application/json",
        ).status_code
        == 403
    )
