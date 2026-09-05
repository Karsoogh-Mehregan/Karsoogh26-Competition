"""Buyouts: paying the floor's buyout price to take a seat from its holder.

The rules being checked here come from the design doc's «مکانیک خرید»:

* the buyer pays a lot — the floor's own `buyout_cost` column;
* the holder is put out but loses nothing already paid;
* the buyer takes the floor and is paid the floor's points;

plus what carries over from movement and duels: the house must be adjacent, the
buyer may not already sit in it, and a seat a judge is about to decide is off
the table.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.boards import Board
from duels.models import Duel, Room
from game.models import (
    AcquisitionSource,
    Edge,
    FloorReward,
    GameSettings,
    GameStatus,
    LevelConfig,
    Node,
    Occupancy,
    ReleaseReason,
)
from game.services.buyout import BuyoutRefused, buy_out, buyable_targets, buyout_cost
from game.services.movement import expandable_node_ids
from teams.models import BalanceEvent, BalanceReason, Team

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def running_game():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture
def levels():
    return {row.pk: row for row in LevelConfig.objects.all()}


@pytest.fixture
def board(levels):
    """A spawn the buyer sits on, wired to a hard house; a second house out of reach."""
    home = Node.objects.create(board=Board.GIRLS, code="S1", name="Home", level=levels["spawn"])
    house = Node.objects.create(
        board=Board.GIRLS, code="H1", name="North Tower", level=levels["hard"]
    )
    away = Node.objects.create(board=Board.GIRLS, code="H2", name="Far Tower", level=levels["hard"])
    first, second = sorted((home, house), key=lambda node: node.pk)
    Edge.objects.create(a=first, b=second)
    return {"home": home, "house": house, "away": away}


@pytest.fixture
def buyer():
    return Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=10_000)


@pytest.fixture
def holder():
    return Team.objects.create(board=Board.GIRLS, code="beta", name="Beta", balance=100)


@pytest.fixture
def seated_buyer(board, buyer):
    return Occupancy.objects.create(team=buyer, node=board["home"], slot=1, is_spawn=True)


@pytest.fixture
def held_floor(board, holder):
    """Floor 2 of H1, owned by the holder. The house is otherwise empty."""
    return Occupancy.objects.create(node=board["house"], team=holder, slot=1, floor=2)


def price(level: str, floor: int) -> FloorReward:
    return FloorReward.objects.get(level_id=level, floor=floor)


class TestTargets:
    def test_an_owned_floor_next_door_is_for_sale(self, board, seated_buyer, held_floor, buyer):
        rows = buyable_targets(buyer)
        assert [row["occupancy_id"] for row in rows] == [held_floor.pk]
        row = rows[0]
        assert row["node_code"] == "H1"
        assert row["floor"] == 2
        assert row["team"] == held_floor.team
        assert row["cost"] == price("hard", 2).buyout_cost
        assert row["points"] == price("hard", 2).points

    def test_a_house_need_not_be_full(self, board, seated_buyer, held_floor, buyer):
        # Unlike a duel: one owned floor in a three-floor house is enough.
        assert board["house"].level.capacity == 3
        assert buyable_targets(buyer)

    def test_a_reservation_is_not_for_sale(self, board, seated_buyer, holder, buyer):
        Occupancy.objects.create(node=board["house"], team=holder, slot=1, floor=None)
        assert buyable_targets(buyer) == []

    def test_a_house_out_of_reach_is_not_for_sale(self, board, seated_buyer, holder, buyer):
        Occupancy.objects.create(node=board["away"], team=holder, slot=1, floor=1)
        assert buyable_targets(buyer) == []

    def test_a_house_the_buyer_sits_in_is_not_for_sale(
        self, board, seated_buyer, held_floor, buyer
    ):
        Occupancy.objects.create(node=board["house"], team=buyer, slot=2, floor=1)
        assert buyable_targets(buyer) == []

    def test_a_seat_under_an_open_duel_is_not_for_sale(
        self, board, seated_buyer, held_floor, buyer, holder
    ):
        judge = User.objects.create_user("judge", password="x")
        room = Room.objects.create(name="R", link="https://skyroom.test/r", mentor=judge)
        third = Team.objects.create(board=Board.GIRLS, code="gamma", name="Gamma")
        Duel.objects.create(
            attacker=third,
            attacked=holder,
            node=board["house"],
            target=held_floor,
            floor=2,
            stake=1,
            room=room,
            mentor=judge,
        )
        assert buyable_targets(buyer) == []

    def test_a_team_with_nothing_to_move_from_sees_nothing(self, board, held_floor, buyer):
        assert buyable_targets(buyer) == []


class TestPricing:
    def test_the_price_is_the_floors_own_column(self, held_floor):
        assert buyout_cost(held_floor) == price("hard", 2).buyout_cost

    def test_retuning_the_column_reprices_the_buyout(self, held_floor):
        FloorReward.objects.filter(level_id="hard", floor=2).update(buyout_cost=12_345)
        assert buyout_cost(held_floor) == 12_345


class TestBuying:
    def test_the_buyer_pays_the_price_and_is_paid_the_points(
        self, running_game, board, seated_buyer, held_floor, buyer
    ):
        reward = price("hard", 2)
        before = buyer.balance

        holding = buy_out(buyer, held_floor.pk)

        buyer.refresh_from_db()
        assert buyer.balance == before - reward.buyout_cost + reward.points
        assert holding.team == buyer
        assert holding.node == board["house"]
        assert holding.slot == held_floor.slot
        assert holding.floor == 2
        assert holding.source == AcquisitionSource.BUYOUT
        assert holding.grade is None

        events = list(BalanceEvent.objects.filter(team=buyer).order_by("pk"))
        assert [event.delta for event in events] == [-reward.buyout_cost, reward.points]
        assert {event.reason for event in events} == {BalanceReason.BUYOUT}
        assert "H1 f2" in events[0].detail

    def test_the_holder_is_put_out_and_keeps_its_money(
        self, running_game, board, seated_buyer, held_floor, buyer, holder
    ):
        buy_out(buyer, held_floor.pk)

        held_floor.refresh_from_db()
        holder.refresh_from_db()
        assert held_floor.released_at is not None
        assert held_floor.release_reason == ReleaseReason.BOUGHT_OUT
        assert holder.balance == 100
        assert not BalanceEvent.objects.filter(team=holder).exists()

    def test_a_bought_floor_expands_reach_without_a_grade(
        self, running_game, board, seated_buyer, held_floor, buyer
    ):
        buy_out(buyer, held_floor.pk)
        assert board["house"].pk in expandable_node_ids(buyer)

    def test_the_game_must_be_running(self, board, seated_buyer, held_floor, buyer):
        with pytest.raises(BuyoutRefused):
            buy_out(buyer, held_floor.pk)

    def test_a_team_cannot_buy_its_own_seat(self, running_game, board, seated_buyer, buyer):
        own = Occupancy.objects.create(node=board["house"], team=buyer, slot=1, floor=1)
        with pytest.raises(BuyoutRefused):
            buy_out(buyer, own.pk)

    def test_a_reservation_cannot_be_bought(self, running_game, board, seated_buyer, holder, buyer):
        reservation = Occupancy.objects.create(node=board["house"], team=holder, slot=1)
        with pytest.raises(BuyoutRefused):
            buy_out(buyer, reservation.pk)

    def test_a_house_out_of_reach_cannot_be_bought(
        self, running_game, board, seated_buyer, holder, buyer
    ):
        far = Occupancy.objects.create(node=board["away"], team=holder, slot=1, floor=1)
        with pytest.raises(BuyoutRefused):
            buy_out(buyer, far.pk)

    def test_a_team_with_a_seat_in_the_house_cannot_buy_its_neighbours(
        self, running_game, board, seated_buyer, held_floor, buyer
    ):
        Occupancy.objects.create(node=board["house"], team=buyer, slot=2, floor=1)
        with pytest.raises(BuyoutRefused):
            buy_out(buyer, held_floor.pk)

    def test_a_spawn_cannot_be_bought(self, running_game, board, seated_buyer, buyer, holder):
        other_spawn = Node.objects.create(
            board=Board.GIRLS, code="S2", level=LevelConfig.objects.get(pk="spawn")
        )
        Edge.objects.create(
            a=min(board["home"], other_spawn, key=lambda n: n.pk),
            b=max(board["home"], other_spawn, key=lambda n: n.pk),
        )
        seat = Occupancy.objects.create(node=other_spawn, team=holder, slot=1, floor=1)
        with pytest.raises(BuyoutRefused):
            buy_out(buyer, seat.pk)

    def test_a_team_that_cannot_pay_is_refused_and_not_charged(
        self, running_game, board, seated_buyer, held_floor, buyer
    ):
        Team.objects.filter(pk=buyer.pk).update(balance=1)
        buyer.refresh_from_db()
        with pytest.raises(BuyoutRefused):
            buy_out(buyer, held_floor.pk)
        buyer.refresh_from_db()
        assert buyer.balance == 1
        held_floor.refresh_from_db()
        assert held_floor.released_at is None
        assert not BalanceEvent.objects.filter(team=buyer).exists()

    def test_a_released_seat_cannot_be_bought_twice(
        self, running_game, board, seated_buyer, held_floor, buyer
    ):
        buy_out(buyer, held_floor.pk)
        other = Team.objects.create(board=Board.GIRLS, code="gamma", name="Gamma", balance=10_000)
        spawn = Node.objects.create(
            board=Board.GIRLS, code="S2", level=LevelConfig.objects.get(pk="spawn")
        )
        Edge.objects.create(
            a=min(spawn, board["house"], key=lambda n: n.pk),
            b=max(spawn, board["house"], key=lambda n: n.pk),
        )
        Occupancy.objects.create(team=other, node=spawn, slot=1, is_spawn=True)
        with pytest.raises(BuyoutRefused):
            buy_out(other, held_floor.pk)


class TestApi:
    @pytest.fixture
    def player(self, buyer):
        user = User.objects.create_user("u-alpha", password="secret", team=buyer)
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_targets_endpoint_lists_the_purchasable_floors(
        self, running_game, board, seated_buyer, held_floor, player
    ):
        response = player.get("/api/buyouts/targets/")
        assert response.status_code == 200
        [row] = response.json()
        assert row["occupancy_id"] == held_floor.pk
        assert row["team"] == {"code": "beta", "name": "Beta", "color": None}
        assert row["cost"] == price("hard", 2).buyout_cost
        assert row["points"] == price("hard", 2).points

    def test_posting_a_purchase_seats_the_buyer(
        self, running_game, board, seated_buyer, held_floor, player, buyer
    ):
        response = player.post("/api/buyouts/", {"occupancy": held_floor.pk}, format="json")
        assert response.status_code == 201
        body = response.json()
        assert body["holding"]["node"]["code"] == "H1"
        assert body["holding"]["floor"] == 2
        buyer.refresh_from_db()
        assert body["balance"] == buyer.balance

        teams = player.get("/api/teams/").json()
        mine = next(team for team in teams if team["code"] == "alpha")
        [bought] = [h for h in mine["holdings"] if h["node_code"] == "H1"]
        assert bought["source"] == "buyout"
        assert bought["floor"] == 2

    def test_a_refused_purchase_answers_409_with_a_reason(
        self, running_game, board, seated_buyer, holder, player
    ):
        far = Occupancy.objects.create(node=board["away"], team=holder, slot=1, floor=1)
        response = player.post("/api/buyouts/", {"occupancy": far.pk}, format="json")
        assert response.status_code == 409
        assert "مجاور" in response.json()["detail"]

    def test_the_game_must_be_running_over_the_api(self, board, seated_buyer, held_floor, player):
        response = player.post("/api/buyouts/", {"occupancy": held_floor.pk}, format="json")
        assert response.status_code == 403

    def test_an_organiser_has_no_team_to_buy_for(self, running_game):
        staff = User.objects.create_user("staff", password="secret", is_staff=True)
        client = APIClient()
        client.force_authenticate(staff)
        assert client.get("/api/buyouts/targets/").status_code == 403
        assert client.post("/api/buyouts/", {"occupancy": 1}, format="json").status_code == 403
