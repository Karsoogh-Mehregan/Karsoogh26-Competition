"""The wall between the two contests.

Both boards hold a full copy of the map under the same node codes, so almost
every rule here is about a code resolving to a different row depending on who
is asking. What a girls team may reach, rank against, duel or be matched with
must never cross into the boys' contest, and vice versa.
"""

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.boards import Board, CrossBoard, require_same_board
from duels.services import challengeable_targets
from events.models import EventCode, MatchmakingStatus, MatchmakingTicket
from events.services import create_auction_event, join_matchmaking
from game.models import (
    AnswerType,
    Edge,
    GameSettings,
    GameStatus,
    LevelConfig,
    Node,
    Occupancy,
    Question,
)
from game.services import restart_game
from game.sse import Frame, _visible_to
from teams.models import BalanceEvent, Team
from teams.start_colors import color_for_start

pytestmark = pytest.mark.django_db

START_CODE = "L1_0"
CODES = {START_CODE: "spawn", "e1": "easy", "e2": "easy"}


def _map(board: str) -> dict[str, Node]:
    """One board's copy of a tiny map: spawn -- e1 -- e2."""
    levels = {row.pk: row for row in LevelConfig.objects.all()}
    nodes = {
        code: Node.objects.create(board=board, code=code, name=code, level=levels[level])
        for code, level in CODES.items()
    }
    for first, second in ((START_CODE, "e1"), ("e1", "e2")):
        a, b = sorted((nodes[first], nodes[second]), key=lambda node: node.pk)
        Edge.objects.create(a=a, b=b)
    return nodes


def _team(board: str, code: str, *, spawned=True) -> Team:
    team = Team.objects.create(
        board=board,
        code=code,
        name=code.title(),
        balance=500,
        color=color_for_start(START_CODE) if spawned else None,
    )
    return team


def _client(django_user_model, team: Team) -> APIClient:
    user = django_user_model.objects.create_user(f"user-{team.code}", password="x", team=team)
    client = APIClient()
    client.force_authenticate(user)
    return client


def _mentor_client(django_user_model) -> APIClient:
    user = django_user_model.objects.create_user("mentor", password="x")
    user.groups.add(Group.objects.get(name="Mentors"))
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def running_game():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture
def both_maps():
    return {board: _map(board) for board in Board.values}


@pytest.fixture
def easy_questions():
    """A pool deep enough that a reservation actually gets a question."""
    return [
        Question.objects.create(
            level_id="easy",
            code=f"q{index}",
            title=f"Q{index}",
            body="?",
            answer_type=AnswerType.TEXT,
        )
        for index in range(4)
    ]


class TestTheMapIsTwoCopies:
    def test_the_same_code_exists_once_per_board(self, both_maps):
        assert Node.objects.filter(code=START_CODE).count() == 2
        assert {node.board for node in Node.objects.filter(code=START_CODE)} == set(Board.values)

    def test_a_code_is_still_unique_within_one_board(self, both_maps):
        spawn = LevelConfig.objects.get(pk="spawn")
        with pytest.raises(IntegrityError), transaction.atomic():
            Node.objects.create(board=Board.GIRLS, code=START_CODE, level=spawn)

    def test_a_blank_board_is_refused(self):
        spawn = LevelConfig.objects.get(pk="spawn")
        with pytest.raises(IntegrityError), transaction.atomic():
            Node.objects.create(board="", code="nowhere", level=spawn)


class TestTeamsAreScopedToTheirBoard:
    def test_both_boards_can_hold_the_same_start_colour(self, both_maps):
        _team(Board.GIRLS, "alpha")
        _team(Board.BOYS, "bravo")
        assert Team.objects.filter(color=color_for_start(START_CODE)).count() == 2

    def test_one_board_still_cannot_hand_a_colour_out_twice(self, both_maps):
        _team(Board.GIRLS, "alpha")
        with pytest.raises(IntegrityError), transaction.atomic():
            _team(Board.GIRLS, "second")

    def test_each_board_runs_its_own_draft_order(self, both_maps):
        girls = _team(Board.GIRLS, "alpha")
        boys = _team(Board.BOYS, "bravo")
        Team.objects.filter(pk=girls.pk).update(draft_order=1)
        # Would collide on the old table-wide unique.
        Team.objects.filter(pk=boys.pk).update(draft_order=1)
        assert Team.objects.filter(draft_order=1).count() == 2


class TestANodeCodeResolvesInsideTheCallersBoard:
    def test_a_team_cannot_reserve_the_other_boards_node(
        self, django_user_model, both_maps, running_game, easy_questions
    ):
        girls = _team(Board.GIRLS, "alpha")
        Occupancy.objects.create(
            team=girls, node=both_maps[Board.GIRLS][START_CODE], slot=1, is_spawn=True
        )
        client = _client(django_user_model, girls)

        # `e1` exists on both boards; only the girls' copy is reachable, and the
        # boys' copy is not addressable at all.
        response = client.post(
            reverse("game:assign-question", kwargs={"team_code": "alpha", "node_code": "e1"})
        )
        assert response.status_code in (200, 201)
        assert Occupancy.objects.get(team=girls, node__code="e1").node.board == Board.GIRLS
        assert not Occupancy.objects.filter(node__board=Board.BOYS).exists()

    def test_both_boards_can_seat_a_team_on_the_same_start_code(self, both_maps):
        girls = _team(Board.GIRLS, "alpha")
        boys = _team(Board.BOYS, "bravo")
        Occupancy.objects.create(
            team=girls, node=both_maps[Board.GIRLS][START_CODE], slot=1, is_spawn=True
        )
        Occupancy.objects.create(
            team=boys, node=both_maps[Board.BOYS][START_CODE], slot=1, is_spawn=True
        )
        assert Occupancy.objects.active().filter(node__code=START_CODE).count() == 2


class TestReadsAreScoped:
    def test_a_team_only_sees_its_own_boards_teams(self, django_user_model, both_maps):
        girls = _team(Board.GIRLS, "alpha")
        _team(Board.BOYS, "bravo")
        client = _client(django_user_model, girls)

        codes = {row["code"] for row in client.get("/api/teams/").json()}
        assert codes == {"alpha"}

    def test_the_leaderboard_ranks_within_one_board(self, django_user_model, both_maps):
        girls = _team(Board.GIRLS, "alpha")
        boys = _team(Board.BOYS, "bravo")
        Team.objects.filter(pk=boys.pk).update(balance=10_000)

        # Leaderboard is admin-only; a staff viewer on the girls board reads it.
        admin = django_user_model.objects.create_user(
            "boss-alpha", password="x", is_staff=True, team=girls
        )
        client = APIClient()
        client.force_authenticate(admin)
        rows = client.get("/api/leaderboard/").json()
        assert [(row["rank"], row["code"]) for row in rows] == [(1, "alpha")]

    def test_a_mentor_picks_the_board(self, django_user_model, both_maps):
        _team(Board.GIRLS, "alpha")
        _team(Board.BOYS, "bravo")
        client = _mentor_client(django_user_model)

        assert {row["code"] for row in client.get("/api/teams/?board=boys").json()} == {"bravo"}
        assert {row["code"] for row in client.get("/api/teams/?board=girls").json()} == {"alpha"}

    def test_the_design_read_returns_one_boards_nodes(self, django_user_model, both_maps):
        girls = _team(Board.GIRLS, "alpha")
        payload = _client(django_user_model, girls).get("/api/map/design/").json()
        codes = [node["code"] for node in payload["nodes"]]
        assert sorted(codes) == sorted(CODES)


class TestPairingNeverCrossesBoards:
    def test_require_same_board_refuses_a_mixed_pair(self, both_maps):
        girls = _team(Board.GIRLS, "alpha")
        boys = _team(Board.BOYS, "bravo")
        with pytest.raises(CrossBoard):
            require_same_board(girls, boys)
        assert require_same_board(girls) == Board.GIRLS

    def test_matchmaking_leaves_a_lone_other_board_ticket_alone(self, both_maps):
        girls = _team(Board.GIRLS, "alpha")
        boys = _team(Board.BOYS, "bravo")

        join_matchmaking(EventCode.TERRITORY_CONTROL, boys)
        ticket = join_matchmaking(EventCode.TERRITORY_CONTROL, girls)

        # Both are still waiting: the only opponent on offer was on the other board.
        assert ticket.status == MatchmakingStatus.WAITING
        assert MatchmakingTicket.objects.filter(status=MatchmakingStatus.WAITING).count() == 2

    def test_matchmaking_pairs_two_teams_on_one_board(self, both_maps):
        first = _team(Board.GIRLS, "alpha")
        second = _team(Board.GIRLS, "second", spawned=False)

        join_matchmaking(EventCode.TERRITORY_CONTROL, first)
        ticket = join_matchmaking(EventCode.TERRITORY_CONTROL, second)

        assert ticket.status == MatchmakingStatus.MATCHED
        assert ticket.matched_team == first

    def test_an_auction_ranks_and_pairs_inside_one_board(self, both_maps):
        _team(Board.GIRLS, "alpha")
        _team(Board.GIRLS, "second", spawned=False)
        _team(Board.BOYS, "bravo")

        event = create_auction_event(board=Board.GIRLS, now=timezone.now())

        assert event.board == Board.GIRLS
        assert {row["code"] for row in event.ranking_snapshot} == {"alpha", "second"}
        for pair in event.pairs.all():
            assert pair.team_one.board == Board.GIRLS
            assert pair.team_two is None or pair.team_two.board == Board.GIRLS

    def test_duel_targets_stop_at_the_board_edge(self, both_maps):
        girls = _team(Board.GIRLS, "alpha")
        boys = _team(Board.BOYS, "bravo")
        Occupancy.objects.create(
            team=girls, node=both_maps[Board.GIRLS][START_CODE], slot=1, is_spawn=True
        )
        # A full, owned building on the boys' `e1` — reachable by code, not by road.
        Occupancy.objects.create(
            team=boys,
            node=both_maps[Board.BOYS]["e1"],
            slot=1,
            floor=1,
            grade=100,
            grade_multiplier=1,
            question_assigned_at=timezone.now(),
        )

        assert challengeable_targets(girls) == []


class TestSseFramesAreAddressed:
    def _frame(self, board: str) -> Frame:
        return Frame(id="1-0", event="board.graded", payload=b"", mentor_only=False, board=board)

    def test_a_board_frame_is_dropped_for_the_other_board(self):
        frame = self._frame(Board.GIRLS)
        assert _visible_to(frame, is_mentor=False, user_id=1, board=Board.GIRLS)
        assert not _visible_to(frame, is_mentor=False, user_id=1, board=Board.BOYS)

    def test_an_organiser_sees_every_board(self):
        frame = self._frame(Board.GIRLS)
        assert _visible_to(frame, is_mentor=True, user_id=1, board=None)

    def test_an_unaddressed_frame_still_reaches_everyone(self):
        frame = Frame(id="1-0", event="game.state", payload=b"", mentor_only=False)
        assert _visible_to(frame, is_mentor=False, user_id=1, board=Board.BOYS)


class TestRestartCanBeScopedToOneBoard:
    def test_one_board_is_cleared_and_the_other_is_untouched(self, both_maps):
        girls = _team(Board.GIRLS, "alpha")
        boys = _team(Board.BOYS, "bravo")
        for team, board in ((girls, Board.GIRLS), (boys, Board.BOYS)):
            Occupancy.objects.create(
                team=team, node=both_maps[board][START_CODE], slot=1, is_spawn=True
            )
            BalanceEvent.objects.create(
                team=team, delta=-10, balance_after=490, reason="entry", detail="x"
            )

        summary = restart_game(board=Board.GIRLS)

        assert summary["board"] == Board.GIRLS
        assert not Occupancy.objects.filter(team=girls).exists()
        assert Occupancy.objects.filter(team=boys).count() == 1
        assert not BalanceEvent.objects.filter(team=girls).exists()
        assert BalanceEvent.objects.filter(team=boys).count() == 1

    def test_a_scoped_restart_leaves_the_shared_clock_running(self, running_game, both_maps):
        _team(Board.GIRLS, "alpha")
        restart_game(board=Board.GIRLS)
        assert GameSettings.load().status == GameStatus.RUNNING

    def test_an_unscoped_restart_still_stops_the_clock(self, running_game, both_maps):
        _team(Board.GIRLS, "alpha")
        restart_game()
        assert GameSettings.load().status == GameStatus.NOT_STARTED


class TestImportGraphFillsOneBoardAtATime:
    def test_a_second_board_is_a_second_full_copy(self, tmp_path):
        graph = {
            "nodes": [{"id": "L1_0", "type": "start"}, {"id": "L1_1", "type": "l1"}],
            "edges": [{"source": "L1_0", "target": "L1_1", "directed": False}],
        }
        import json

        path = tmp_path / "graph.json"
        path.write_text(json.dumps(graph), encoding="utf-8")

        call_command("import_graph", board=Board.BOYS, file=path)
        assert Node.objects.count() == 2

        call_command("import_graph", board=Board.GIRLS, file=path)
        assert Node.objects.count() == 4
        assert Edge.objects.count() == 2
        for edge in Edge.objects.select_related("a", "b"):
            assert edge.a.board == edge.b.board
