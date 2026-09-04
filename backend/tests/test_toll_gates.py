"""A toll node is a gate in the road, crossed by beating its Minesweeper board.

The gate is what makes the outer rings reachable at all: every road into ring 4
runs through a `C34` node and every road into ring 5 through a `C45`, one-way in
both cases. A gate takes no question and seats nobody — it charges a fee, hands
out a board, and a win opens the road past it for that team, permanently, for
however many teams beat it.
"""

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from game.models import Edge, GameSettings, GameStatus, LevelConfig, Node, Occupancy
from game.services.mentor import Conflict
from game.services.movement import claim_node, expandable_node_ids, is_reachable
from minesweeper.crossings import cleared_node_codes, has_cleared, open_board_node_codes
from minesweeper.exceptions import AlreadyCleared, EntryFeeUnaffordable, NodeUnreachable
from minesweeper.models import (
    DifficultyConfig,
    MinesweeperAttempt,
    MinesweeperDifficulty,
    MinesweeperSettings,
    MinesweeperStatus,
)
from minesweeper.services import (
    default_toll_difficulty,
    ensure_toll_boards,
    issue_entry,
    reveal_cell,
    start_play,
)
from teams.models import BalanceReason, Team

pytestmark = pytest.mark.django_db

TOLL_COST = 30


@pytest.fixture
def running_game():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture
def road():
    """L3_0 -> C34_0 -> L4_0: the map's real shape, one-way through the gate."""
    levels = {row.pk: row for row in LevelConfig.objects.all()}
    near = Node.objects.create(code="L3_0", name="Near", level=levels["medium"])
    gate = Node.objects.create(code="C34_0", name="Gate", level=levels["toll"])
    far = Node.objects.create(code="L4_0", name="Far", level=levels["medium"])
    Edge.objects.create(a=near, b=gate, directed=True)
    Edge.objects.create(a=gate, b=far, directed=True)
    MinesweeperSettings.objects.create(node=gate, difficulty_id=MinesweeperDifficulty.EASY)
    return {"near": near, "gate": gate, "far": far}


@pytest.fixture
def team():
    return Team.objects.create(code="alpha", name="Alpha", balance=400)


@pytest.fixture
def other_team():
    return Team.objects.create(code="beta", name="Beta", balance=400)


def seat(team, node, slot=1):
    """Put a team on the road beside the gate, as a spawn, so its reach expands."""
    return Occupancy.objects.create(node=node, team=team, slot=slot, is_spawn=True)


def win(attempt):
    """Finish an attempt the way a last safe reveal does, without playing it out."""
    attempt.status = MinesweeperStatus.WON
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=["status", "finished_at"])
    return attempt


def lose(attempt):
    MinesweeperAttempt.objects.filter(pk=attempt.pk).update(
        status=MinesweeperStatus.LOST, finished_at=timezone.now()
    )


class TestEnteringAGate:
    def test_gate_must_be_adjacent(self, team, road, running_game):
        seat(
            team,
            Node.objects.create(
                code="elsewhere", name="Elsewhere", level=LevelConfig.objects.get(level="easy")
            ),
        )
        with pytest.raises(NodeUnreachable):
            start_play(road["gate"], team)
        assert MinesweeperAttempt.objects.count() == 0

    def test_a_team_with_nothing_cannot_enter(self, team, road, running_game):
        assert expandable_node_ids(team) == set()
        with pytest.raises(NodeUnreachable):
            start_play(road["gate"], team)

    def test_entering_charges_the_toll(self, team, road, running_game):
        seat(team, road["near"])
        start_play(road["gate"], team)

        team.refresh_from_db()
        assert team.balance == 400 - TOLL_COST
        event = team.balance_events.latest("id")
        assert (event.reason, event.detail, event.delta) == (
            BalanceReason.TOLL,
            "C34_0",
            -TOLL_COST,
        )

    def test_resuming_the_same_board_is_free(self, team, road, running_game):
        seat(team, road["near"])
        first = start_play(road["gate"], team)
        second = start_play(road["gate"], team)

        assert second.pk == first.pk
        team.refresh_from_db()
        assert team.balance == 400 - TOLL_COST

    def test_an_open_board_resumes_even_without_the_holding_it_came_from(
        self, team, road, running_game
    ):
        """Bought and unfinished: leaving the road it was reached from is not
        a reason to lose a board the team already paid for."""
        holding = seat(team, road["near"])
        first = start_play(road["gate"], team)
        Occupancy.objects.filter(pk=holding.pk).update(released_at=timezone.now())

        assert expandable_node_ids(team) == set()
        assert open_board_node_codes(team) == ["C34_0"]
        # Both halves of the flow: the map click and the board itself.
        issue_entry({}, user_id=1, node=road["gate"], team=team)
        assert start_play(road["gate"], team).pk == first.pk
        team.refresh_from_db()
        assert team.balance == 400 - TOLL_COST

    def test_a_finished_board_is_no_longer_open(self, team, road, running_game):
        seat(team, road["near"])
        attempt = start_play(road["gate"], team)
        assert open_board_node_codes(team) == ["C34_0"]

        win(attempt)
        assert open_board_node_codes(team) == []

    def test_a_new_board_after_a_loss_charges_again(self, team, road, running_game):
        seat(team, road["near"])
        lose(start_play(road["gate"], team))

        start_play(road["gate"], team)
        team.refresh_from_db()
        assert team.balance == 400 - 2 * TOLL_COST

    def test_a_team_that_cannot_pay_gets_no_board(self, team, road, running_game):
        seat(team, road["near"])
        Team.objects.filter(pk=team.pk).update(balance=TOLL_COST - 1)

        with pytest.raises(EntryFeeUnaffordable):
            start_play(road["gate"], team)
        assert MinesweeperAttempt.objects.count() == 0

    def test_a_cleared_gate_cannot_be_paid_for_twice(self, team, road, running_game):
        seat(team, road["near"])
        win(start_play(road["gate"], team))

        with pytest.raises(AlreadyCleared):
            start_play(road["gate"], team)
        team.refresh_from_db()
        assert team.balance == 400 - TOLL_COST


class TestCrossing:
    def test_winning_opens_the_road_past_the_gate(self, team, road, running_game):
        seat(team, road["near"])
        assert not is_reachable(road["far"], expandable_node_ids(team))

        win(start_play(road["gate"], team))

        assert has_cleared(team, road["gate"])
        assert road["gate"].pk in expandable_node_ids(team)
        assert is_reachable(road["far"], expandable_node_ids(team))

    def test_playing_the_board_out_opens_the_road(self, team, road, running_game):
        """The same thing, through `reveal_cell` rather than a hand-set status."""
        DifficultyConfig.objects.create(
            key="tiny", label="ریز", width=2, height=2, mine_count=1, base_score=10
        )
        MinesweeperSettings.objects.filter(node=road["gate"]).update(difficulty_id="tiny")
        seat(team, road["near"])

        attempt = start_play(road["gate"], team)
        cells = attempt.game.board["cells"]
        safe = [(r, c) for r in range(2) for c in range(2) if not cells[r][c]["mine"]]
        for row, col in safe:
            attempt = reveal_cell(attempt.pk, row, col)

        assert attempt.status == MinesweeperStatus.WON
        assert is_reachable(road["far"], expandable_node_ids(team))

    def test_losing_leaves_the_road_shut(self, team, road, running_game):
        seat(team, road["near"])
        lose(start_play(road["gate"], team))

        assert not has_cleared(team, road["gate"])
        assert not is_reachable(road["far"], expandable_node_ids(team))

    def test_the_gate_seats_nobody_and_has_no_capacity(self, team, other_team, road, running_game):
        seat(team, road["near"])
        seat(other_team, road["near"], slot=2)

        for playing in (team, other_team):
            win(start_play(road["gate"], playing))

        assert Occupancy.objects.filter(node=road["gate"]).count() == 0
        assert has_cleared(team, road["gate"])
        assert has_cleared(other_team, road["gate"])

    def test_a_crossing_belongs_to_the_team_that_earned_it(
        self, team, other_team, road, running_game
    ):
        seat(team, road["near"])
        seat(other_team, road["near"], slot=2)
        win(start_play(road["gate"], team))

        assert cleared_node_codes(team) == ["C34_0"]
        assert cleared_node_codes(other_team) == []
        assert not is_reachable(road["far"], expandable_node_ids(other_team))


class TestGateIsNotAnswered:
    def test_claiming_a_gate_with_a_question_is_refused(self, team, road, running_game):
        seat(team, road["near"])
        with pytest.raises(Conflict, match="مین‌روب"):
            claim_node(team, road["gate"])
        assert Occupancy.objects.filter(node=road["gate"]).count() == 0

    def test_the_far_node_is_out_of_reach_until_the_gate_is_cleared(self, team, road, running_game):
        seat(team, road["near"])
        with pytest.raises(Conflict, match="متصل"):
            claim_node(team, road["far"])

        win(start_play(road["gate"], team))
        # Reach is what the gate grants; whether a question is waiting on the far
        # node is a different story, so assert on reach rather than on a claim.
        assert is_reachable(road["far"], expandable_node_ids(team))


class TestBoardApi:
    def test_teams_list_reports_crossings(self, team, road, running_game):
        seat(team, road["near"])
        win(start_play(road["gate"], team))

        user = get_user_model().objects.create_user("alpha-user", password="pw", team=team)
        client = APIClient()
        client.force_authenticate(user)

        rows = {row["code"]: row for row in client.get("/api/teams/").json()}
        assert rows["alpha"]["crossings"] == ["C34_0"]
        assert rows["alpha"]["open_boards"] == []

    def test_teams_list_reports_an_open_board(self, team, road, running_game):
        seat(team, road["near"])
        start_play(road["gate"], team)

        user = get_user_model().objects.create_user("alpha-user", password="pw", team=team)
        client = APIClient()
        client.force_authenticate(user)

        rows = {row["code"]: row for row in client.get("/api/teams/").json()}
        assert rows["alpha"]["open_boards"] == ["C34_0"]
        assert rows["alpha"]["crossings"] == []


class TestProvisioning:
    def test_every_gate_gets_a_board(self, road):
        MinesweeperSettings.objects.all().delete()
        counts = ensure_toll_boards()

        assert counts["created"] == 1
        assert MinesweeperSettings.objects.get(node=road["gate"]).enabled is True

    def test_running_twice_changes_nothing(self, road):
        MinesweeperSettings.objects.filter(node=road["gate"]).update(
            difficulty_id=MinesweeperDifficulty.HARD, enabled=False
        )
        counts = ensure_toll_boards()

        settings = MinesweeperSettings.objects.get(node=road["gate"])
        assert counts == {"created": 0, "updated": 0, "unchanged": 1}
        assert settings.difficulty_id == MinesweeperDifficulty.HARD
        assert settings.enabled is False

    def test_bulk_retune_moves_every_gate(self, road):
        counts = ensure_toll_boards(difficulty=MinesweeperDifficulty.HARD)

        assert counts["updated"] == 1
        assert (
            MinesweeperSettings.objects.get(node=road["gate"]).difficulty_id
            == MinesweeperDifficulty.HARD
        )

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("C34_0", MinesweeperDifficulty.EASY),
            ("C45_7", MinesweeperDifficulty.MEDIUM),
            ("WHAT_1", MinesweeperDifficulty.EASY),
        ],
    )
    def test_default_difficulty_follows_the_ring_the_gate_joins(self, code, expected):
        assert default_toll_difficulty(code) == expected


class TestDifficultyIsData:
    def test_a_retuned_difficulty_reshapes_the_next_board(self, team, road, running_game):
        seat(team, road["near"])
        DifficultyConfig.objects.filter(pk=MinesweeperDifficulty.EASY).update(
            width=12, height=7, mine_count=11, base_score=42
        )

        attempt = start_play(road["gate"], team)

        assert (attempt.game.width, attempt.game.height) == (12, 7)
        assert attempt.game.mine_count == 11
        assert attempt.game.base_score == 42
        assert len(attempt.game.board["cells"]) == 7
        assert sum(cell["mine"] for row in attempt.game.board["cells"] for cell in row) == 11

    def test_a_missing_default_difficulty_still_provisions(self, road):
        MinesweeperSettings.objects.all().delete()
        DifficultyConfig.objects.exclude(pk=MinesweeperDifficulty.HARD).delete()

        counts = ensure_toll_boards()

        assert counts["created"] == 1
        assert (
            MinesweeperSettings.objects.get(node=road["gate"]).difficulty_id
            == MinesweeperDifficulty.HARD
        )
