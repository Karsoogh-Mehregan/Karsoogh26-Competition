"""Duels: challenging a full building next door for one of its floors.

The rules being checked here come from the design doc:

* you may only challenge a house whose every floor already has an owner;
* you must be adjacent to it;
* you pay the entry up front, get it back if you win, and lose it to the
  defender if you do not;
* the winner takes the floor with no question to answer;
* one live duel per team at a time, counting both roles, and a rest window
  after each one;
* a duel with no free judge is refused rather than queued.

The judge decides the result and nothing else — there is no draw path and no
server-side clock, because the meeting is run by a person.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework.test import APIClient

from duels.exceptions import (
    AlreadyInDuel,
    BuildingNotFull,
    InvalidTarget,
    NoRoomAvailable,
    NotAdjacent,
    OnCooldown,
    StakeUnaffordable,
)
from duels.models import Duel, DuelStatus, Room
from duels.services import (
    building_is_full,
    challengeable_targets,
    duel_cost,
    next_room,
    request_duel,
    resolve_duel,
)
from game.models import (
    AcquisitionSource,
    Edge,
    GameSettings,
    GameStatus,
    LevelConfig,
    Node,
    Occupancy,
    ReleaseReason,
)
from notifications.models import Notification
from teams.models import BalanceReason, Team

pytestmark = pytest.mark.django_db

User = get_user_model()

# hard floor 2, from the doc's table (game/migrations/0024).
HARD_FLOOR_2_COST = 1600


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
    """A spawn the attacker sits on, wired to a hard house with three floors."""
    home = Node.objects.create(code="S1", name="Home", level=levels["spawn"])
    house = Node.objects.create(code="H1", name="North Tower", level=levels["hard"])
    away = Node.objects.create(code="H2", name="Far Tower", level=levels["hard"])
    for a, b in ((home, house), (home, away)):
        first, second = sorted((a, b), key=lambda node: node.pk)
        Edge.objects.create(a=first, b=second)
    return {"home": home, "house": house, "away": away}


@pytest.fixture
def attacker():
    return Team.objects.create(code="alpha", name="Alpha", balance=5000)


@pytest.fixture
def defenders():
    return [
        Team.objects.create(code=f"d{index}", name=f"Defender {index}", balance=100)
        for index in range(1, 4)
    ]


@pytest.fixture
def judge():
    user = User.objects.create_user("judge1", password="secret")
    user.user_permissions.add(Permission.objects.get(codename="judge_duel"))
    return user


@pytest.fixture
def room(judge):
    return Room.objects.create(name="Room 1", link="https://skyroom.test/duel-1", mentor=judge)


def seat(node, team, *, slot, floor, source=AcquisitionSource.ATTEMPT):
    return Occupancy.objects.create(node=node, team=team, slot=slot, floor=floor, source=source)


@pytest.fixture
def full_house(board, defenders):
    """All three floors of H1 owned, one defender each."""
    return [
        seat(board["house"], team, slot=index, floor=index)
        for index, team in enumerate(defenders, start=1)
    ]


@pytest.fixture
def seated_attacker(board, attacker):
    return Occupancy.objects.create(team=attacker, node=board["home"], slot=1, is_spawn=True)


class TestEligibility:
    def test_a_full_house_is_one_where_every_floor_has_an_owner(self, board, full_house):
        assert building_is_full(board["house"]) is True

    def test_a_house_with_an_ungraded_reservation_is_not_full(self, board, full_house):
        """Capacity is reached, but the third seat owns nothing yet."""
        full_house[2].floor = None
        full_house[2].save(update_fields=["floor"])
        assert building_is_full(board["house"]) is False

    def test_a_half_empty_house_is_not_full(self, board, defenders):
        seat(board["house"], defenders[0], slot=1, floor=1)
        assert building_is_full(board["house"]) is False

    def test_targets_list_every_floor_of_the_neighbouring_full_house(
        self, running_game, board, attacker, full_house, seated_attacker
    ):
        rows = challengeable_targets(attacker)
        assert {row["floor"] for row in rows} == {1, 2, 3}
        assert {row["node_code"] for row in rows} == {"H1"}
        assert {row["cost"] for row in rows} == {1440, 1600, 1760}

    def test_targets_exclude_a_full_house_that_is_not_adjacent(
        self, running_game, board, attacker, defenders, seated_attacker
    ):
        """H2 is wired to home too, so unseat the attacker to make it unreachable."""
        seated_attacker.released_at = timezone.now()
        seated_attacker.save(update_fields=["released_at"])
        for index, team in enumerate(defenders, start=1):
            seat(board["away"], team, slot=index, floor=index)
        assert challengeable_targets(attacker) == []

    def test_targets_exclude_a_house_the_attacker_already_sits_on(
        self, running_game, board, attacker, defenders, seated_attacker, levels
    ):
        """Winning would seat one team twice on one building."""
        small = Node.objects.create(code="E1", name="Cottage", level=levels["easy"])
        first, second = sorted((board["home"], small), key=lambda node: node.pk)
        Edge.objects.create(a=first, b=second)
        seat(small, attacker, slot=1, floor=1)
        assert [row for row in challengeable_targets(attacker) if row["node_code"] == "E1"] == []

    def test_targets_exclude_a_defender_already_in_a_duel(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        """The busy defender drops out; its neighbours in the same house do not.

        One live duel is a rule about *teams*, not about buildings, so a house
        with one floor under attack is still open on its other two.
        """
        request_duel(attacker, full_house[1].pk)
        other = Team.objects.create(code="gamma", name="Gamma", balance=5000)
        Occupancy.objects.create(team=other, node=board["home"], slot=2, is_spawn=True)
        assert {row["floor"] for row in challengeable_targets(other)} == {1, 3}


class TestPricing:
    def test_the_price_comes_from_the_docs_table_not_the_factor(self, board, full_house):
        """easy 400, medium 720/900, hard 1440/1600/1760 — no single factor fits."""
        assert duel_cost(full_house[1]) == HARD_FLOOR_2_COST

    def test_an_override_cleared_in_admin_falls_back_to_the_level_factor(self, board, full_house):
        from game.models import FloorReward

        FloorReward.objects.filter(level_id="hard", floor=2).update(duel_cost_override=None)
        # hard duel_factor is 1.50 and floor 2 is worth 450.
        assert duel_cost(full_house[1]) == 675


class TestRequesting:
    def test_a_challenge_charges_the_stake_and_books_a_judge(
        self, running_game, board, attacker, full_house, seated_attacker, room, judge
    ):
        duel = request_duel(attacker, full_house[1].pk)

        attacker.refresh_from_db()
        assert attacker.balance == 5000 - HARD_FLOOR_2_COST
        assert duel.stake == HARD_FLOOR_2_COST
        assert duel.status == DuelStatus.OPEN
        assert duel.mentor == judge
        assert duel.room == room
        assert duel.floor == 2
        assert attacker.balance_events.filter(reason=BalanceReason.DUEL).count() == 1

    def test_the_room_goes_to_the_back_of_the_queue(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        assert room.last_assigned_at is None
        request_duel(attacker, full_house[1].pk)
        room.refresh_from_db()
        assert room.last_assigned_at is not None

    def test_a_house_that_is_not_full_cannot_be_challenged(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        full_house[2].floor = None
        full_house[2].save(update_fields=["floor"])
        with pytest.raises(BuildingNotFull):
            request_duel(attacker, full_house[1].pk)

    def test_a_house_that_is_not_adjacent_cannot_be_challenged(
        self, running_game, board, attacker, defenders, seated_attacker, room
    ):
        seated_attacker.released_at = timezone.now()
        seated_attacker.save(update_fields=["released_at"])
        target = seat(board["away"], defenders[0], slot=1, floor=1)
        for index, team in enumerate(defenders[1:], start=2):
            seat(board["away"], team, slot=index, floor=index)
        with pytest.raises(NotAdjacent):
            request_duel(attacker, target.pk)

    def test_a_team_cannot_challenge_its_own_seat(
        self, running_game, board, attacker, seated_attacker, room, defenders
    ):
        mine = seat(board["house"], attacker, slot=1, floor=1)
        seat(board["house"], defenders[0], slot=2, floor=2)
        seat(board["house"], defenders[1], slot=3, floor=3)
        with pytest.raises(InvalidTarget):
            request_duel(attacker, mine.pk)

    def test_a_team_with_a_seat_in_the_house_cannot_duel_its_neighbours(
        self, running_game, board, attacker, seated_attacker, room, defenders
    ):
        seat(board["house"], attacker, slot=1, floor=1)
        target = seat(board["house"], defenders[0], slot=2, floor=2)
        seat(board["house"], defenders[1], slot=3, floor=3)
        with pytest.raises(InvalidTarget):
            request_duel(attacker, target.pk)

    def test_only_one_live_duel_per_team(
        self, running_game, board, attacker, full_house, seated_attacker, room, judge
    ):
        Room.objects.create(name="Room 2", link="https://skyroom.test/duel-2", mentor=judge)
        request_duel(attacker, full_house[1].pk)
        with pytest.raises(AlreadyInDuel):
            request_duel(attacker, full_house[2].pk)

    def test_a_defender_already_defending_cannot_be_challenged_again(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        other = Team.objects.create(code="gamma", name="Gamma", balance=5000)
        Occupancy.objects.create(team=other, node=board["home"], slot=2, is_spawn=True)
        second_judge = User.objects.create_user("judge2", password="secret")
        second_judge.user_permissions.add(Permission.objects.get(codename="judge_duel"))
        Room.objects.create(name="Room 2", link="https://skyroom.test/duel-2", mentor=second_judge)

        request_duel(attacker, full_house[1].pk)
        with pytest.raises(AlreadyInDuel):
            request_duel(other, full_house[1].pk)

    def test_a_team_still_resting_cannot_duel(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        attacker.last_duel_at = timezone.now()
        attacker.save(update_fields=["last_duel_at"])
        with pytest.raises(OnCooldown):
            request_duel(attacker, full_house[1].pk)

    def test_a_lapsed_rest_window_lets_the_team_duel_again(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        minutes = GameSettings.load().duel_cooldown_minutes
        attacker.last_duel_at = timezone.now() - timezone.timedelta(minutes=minutes + 1)
        attacker.save(update_fields=["last_duel_at"])
        assert request_duel(attacker, full_house[1].pk).pk is not None

    def test_a_team_that_cannot_pay_is_refused_and_not_charged(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        Team.objects.filter(pk=attacker.pk).update(balance=10)
        attacker.refresh_from_db()
        with pytest.raises(StakeUnaffordable):
            request_duel(attacker, full_house[1].pk)
        attacker.refresh_from_db()
        assert attacker.balance == 10
        assert not Duel.objects.exists()

    def test_no_free_judge_refuses_the_duel_and_refunds_nothing(
        self, running_game, board, attacker, full_house, seated_attacker
    ):
        """No Room at all: the challenge is rejected, not queued."""
        with pytest.raises(NoRoomAvailable):
            request_duel(attacker, full_house[1].pk)
        attacker.refresh_from_db()
        assert attacker.balance == 5000
        assert not Duel.objects.exists()

    def test_a_busy_judge_is_not_offered_twice(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        other = Team.objects.create(code="gamma", name="Gamma", balance=5000)
        Occupancy.objects.create(team=other, node=board["home"], slot=2, is_spawn=True)
        request_duel(attacker, full_house[1].pk)
        with pytest.raises(NoRoomAvailable):
            request_duel(other, full_house[2].pk)


class TestTheJudgeQueue:
    def test_rotation_is_least_recently_used(self, judge):
        second = User.objects.create_user("judge2", password="secret")
        second.user_permissions.add(Permission.objects.get(codename="judge_duel"))
        first_room = Room.objects.create(name="A", link="https://skyroom.test/a", mentor=judge)
        second_room = Room.objects.create(name="B", link="https://skyroom.test/b", mentor=second)
        first_room.last_assigned_at = timezone.now()
        first_room.save(update_fields=["last_assigned_at"])

        # B has never been used, so it comes first however the ids fell.
        assert next_room() == second_room
        assert next_room() == first_room

    def test_an_inactive_room_is_skipped(self, judge, room):
        room.is_active = False
        room.save(update_fields=["is_active"])
        with pytest.raises(NoRoomAvailable):
            next_room()

    def test_a_room_whose_judge_lost_the_permission_is_skipped(self, judge, room):
        judge.user_permissions.clear()
        with pytest.raises(NoRoomAvailable):
            next_room()


class TestResolving:
    @pytest.fixture
    def duel(self, running_game, board, attacker, full_house, seated_attacker, room):
        return request_duel(attacker, full_house[1].pk)

    def test_the_attacker_winning_takes_the_floor_and_gets_the_stake_back(
        self, duel, attacker, defenders, board
    ):
        resolve_duel(duel, attacker, by=duel.mentor)

        attacker.refresh_from_db()
        assert attacker.balance == 5000

        lost = Occupancy.objects.get(pk=duel.target_id)
        assert lost.released_at is not None
        assert lost.release_reason == ReleaseReason.DUEL_LOST

        won = Occupancy.objects.active().get(team=attacker, node=board["house"])
        assert (won.floor, won.slot) == (2, 2)
        assert won.source == AcquisitionSource.DUEL
        assert won.question_assigned_at is None  # no question to answer for it

    def test_the_defender_winning_keeps_the_floor_and_takes_the_stake(
        self, duel, attacker, defenders
    ):
        defender = defenders[1]
        resolve_duel(duel, defender, by=duel.mentor)

        attacker.refresh_from_db()
        defender.refresh_from_db()
        assert attacker.balance == 5000 - HARD_FLOOR_2_COST
        assert defender.balance == 100 + HARD_FLOOR_2_COST

        held = Occupancy.objects.get(pk=duel.target_id)
        assert held.released_at is None
        assert held.team_id == defender.pk

    def test_the_ledger_names_the_node_by_code_not_by_id(self, duel, attacker):
        """An organiser reading the wallet log needs «H1 f2», not a primary key."""
        resolve_duel(duel, attacker, by=duel.mentor)
        details = attacker.balance_events.filter(reason=BalanceReason.DUEL).values_list(
            "detail", flat=True
        )
        assert all("H1 f2" in detail for detail in details)

    def test_closing_records_winner_loser_and_judge(self, duel, attacker, defenders):
        closed = resolve_duel(duel, attacker, by=duel.mentor)
        assert closed.status == DuelStatus.CLOSED
        assert closed.winner_id == attacker.pk
        assert closed.loser_id == defenders[1].pk
        assert closed.resolved_by_id == duel.mentor_id
        assert closed.resolved_at is not None

    def test_both_teams_start_resting_when_it_closes(self, duel, attacker, defenders):
        resolve_duel(duel, attacker, by=duel.mentor)
        attacker.refresh_from_db()
        defenders[1].refresh_from_db()
        assert attacker.last_duel_at is not None
        assert defenders[1].last_duel_at is not None

    def test_a_duel_closes_once(self, duel, attacker):
        from duels.exceptions import DuelClosed

        resolve_duel(duel, attacker, by=duel.mentor)
        with pytest.raises(DuelClosed):
            resolve_duel(duel, attacker, by=duel.mentor)

    def test_the_winner_must_be_one_of_the_two_teams(self, duel):
        outsider = Team.objects.create(code="zeta", name="Zeta", balance=0)
        with pytest.raises(InvalidTarget):
            resolve_duel(duel, outsider, by=duel.mentor)

    def test_a_won_floor_expands_reach_without_a_grade(self, duel, attacker, board):
        from game.services.movement import expandable_node_ids

        resolve_duel(duel, attacker, by=duel.mentor)
        assert board["house"].pk in expandable_node_ids(attacker)

    def test_a_won_floor_is_not_offered_a_question(self, duel, attacker, board):
        from game.services.mentor import Conflict
        from game.services.movement import claim_node

        resolve_duel(duel, attacker, by=duel.mentor)
        with pytest.raises(Conflict):
            claim_node(attacker, board["house"])

    def test_a_won_floor_is_owned_not_reserved_over_the_api(self, duel, attacker, board):
        """The shape the SPA reads to tell a reservation from an owned floor.

        A reservation is `floor is None` — the floor is captured at grading, not
        at claiming. A duel win hands over the floor itself, so `floor` is set
        and `grade` stays null because nothing was answered for it. Anything
        keying "reserved" off `grade` instead of `floor` paints this seat as
        scaffolding and offers its owner a question it has already won.
        """
        resolve_duel(duel, attacker, by=duel.mentor)

        client = APIClient()
        client.force_authenticate(
            User.objects.create_user("u-alpha-api", password="secret", team=attacker)
        )
        rows = client.get("/api/teams/").json()
        row = next(team for team in rows if team["code"] == attacker.code)
        holding = next(h for h in row["holdings"] if h["node_code"] == board["house"].code)

        assert holding["floor"] == 2, "a won floor is owned outright"
        assert holding["grade"] is None, "nothing was answered for it"
        assert holding["source"] == AcquisitionSource.DUEL


class TestNotices:
    def test_opening_a_duel_writes_to_both_teams_and_the_judge(
        self, running_game, board, attacker, full_house, seated_attacker, room, judge
    ):
        alpha_user = User.objects.create_user("u-alpha", password="x", team=attacker)
        defender_user = User.objects.create_user(
            "u-defender", password="x", team=full_house[1].team
        )

        duel = request_duel(attacker, full_house[1].pk)

        for user in (alpha_user, defender_user, judge):
            assert Notification.objects.for_user(user).exists(), user

        body = Notification.objects.for_user(alpha_user).first().message.body
        assert room.link in body
        assert str(duel.stake) in body

    def test_closing_a_duel_tells_both_teams_the_result(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        alpha_user = User.objects.create_user("u-alpha", password="x", team=attacker)
        duel = request_duel(attacker, full_house[1].pk)
        resolve_duel(duel, attacker, by=duel.mentor)

        titles = [row.message.title for row in Notification.objects.for_user(alpha_user).inbox()]
        assert any("نتیجهٔ دوئل" in title for title in titles)

    def test_duel_notices_stay_out_of_the_announcers_sent_list(
        self, running_game, board, attacker, full_house, seated_attacker, room
    ):
        """They are delivered, but they are not something a person wrote."""
        announcer = User.objects.create_user("announcer", password="secret")
        announcer.user_permissions.add(Permission.objects.get(codename="send_announcement"))
        client = APIClient()
        client.force_authenticate(announcer)

        request_duel(attacker, full_house[1].pk)

        assert client.get("/api/messages/?status=sent").json() == []


class TestApi:
    @pytest.fixture
    def player(self, attacker):
        user = User.objects.create_user("u-alpha", password="secret", team=attacker)
        client = APIClient()
        client.force_authenticate(user)
        return client

    @pytest.fixture
    def judge_client(self, judge):
        client = APIClient()
        client.force_authenticate(judge)
        return client

    def test_targets_endpoint_lists_the_challengeable_floors(
        self, running_game, board, full_house, seated_attacker, player
    ):
        response = player.get("/api/duels/targets/")
        assert response.status_code == 200
        assert {row["floor"] for row in response.json()} == {1, 2, 3}

    def test_posting_a_challenge_opens_a_duel(
        self, running_game, board, full_house, seated_attacker, room, player
    ):
        response = player.post("/api/duels/", {"occupancy": full_house[1].pk}, format="json")
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "open"
        assert body["my_role"] == "attacker"
        assert body["room_link"] == room.link

    def test_the_list_endpoint_answers_the_whole_page(
        self, running_game, board, full_house, seated_attacker, room, player
    ):
        player.post("/api/duels/", {"occupancy": full_house[1].pk}, format="json")
        body = player.get("/api/duels/").json()
        assert body["active"]["floor"] == 2
        assert body["can_request"] is False
        assert body["blocked_reason"]
        assert body["history"] == []

    def test_a_refused_challenge_answers_409_with_a_reason(
        self, running_game, board, full_house, seated_attacker, player
    ):
        response = player.post("/api/duels/", {"occupancy": full_house[1].pk}, format="json")
        assert response.status_code == 409
        assert "داور" in response.json()["detail"]

    def test_the_judge_sees_the_duel_and_can_call_it(
        self,
        running_game,
        board,
        attacker,
        full_house,
        seated_attacker,
        room,
        player,
        judge_client,
    ):
        created = player.post("/api/duels/", {"occupancy": full_house[1].pk}, format="json").json()

        assigned = judge_client.get("/api/duels/").json()["judging"]
        assert assigned["id"] == created["id"]
        assert assigned["my_role"] == "judge"

        response = judge_client.post(
            f"/api/duels/{created['id']}/resolve/", {"winner": "alpha"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["winner"]["code"] == "alpha"

    def test_another_judge_may_not_call_someone_elses_duel(
        self, running_game, board, full_house, seated_attacker, room, player
    ):
        created = player.post("/api/duels/", {"occupancy": full_house[1].pk}, format="json").json()

        intruder = User.objects.create_user("judge2", password="secret")
        intruder.user_permissions.add(Permission.objects.get(codename="judge_duel"))
        client = APIClient()
        client.force_authenticate(intruder)

        response = client.post(
            f"/api/duels/{created['id']}/resolve/", {"winner": "alpha"}, format="json"
        )
        assert response.status_code == 403

    def test_a_team_may_not_call_its_own_duel(
        self, running_game, board, full_house, seated_attacker, room, player
    ):
        created = player.post("/api/duels/", {"occupancy": full_house[1].pk}, format="json").json()
        response = player.post(
            f"/api/duels/{created['id']}/resolve/", {"winner": "alpha"}, format="json"
        )
        assert response.status_code == 403

    def test_an_outsider_never_sees_the_meeting_link(
        self, running_game, board, full_house, seated_attacker, room, player
    ):
        created = player.post("/api/duels/", {"occupancy": full_house[1].pk}, format="json").json()

        outsider = Team.objects.create(code="zeta", name="Zeta", balance=0)
        user = User.objects.create_user("u-zeta", password="secret", team=outsider)
        client = APIClient()
        client.force_authenticate(user)

        body = client.get(f"/api/duels/{created['id']}/").json()
        assert body["room_link"] is None
        assert body["my_role"] is None

    def test_duels_are_refused_while_the_game_is_not_running(
        self, board, full_house, seated_attacker, room, player
    ):
        response = player.post("/api/duels/", {"occupancy": full_house[1].pk}, format="json")
        assert response.status_code == 409
