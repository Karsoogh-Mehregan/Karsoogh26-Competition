"""Database invariants for MinesweeperGame — not gameplay."""

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from game.models import LevelConfig, Node
from minesweeper.models import (
    DIFFICULTY_LAYOUTS,
    MinesweeperDifficulty,
    MinesweeperGame,
    MinesweeperStatus,
)
from teams.models import Team

pytestmark = pytest.mark.django_db


@pytest.fixture
def team():
    return Team.objects.create(code="alpha", name="Alpha")


@pytest.fixture
def node():
    return Node.objects.create(
        code="ms1",
        name="MS 1",
        level=LevelConfig.objects.get(level="easy"),
    )


def start_game(team, node, difficulty=MinesweeperDifficulty.EASY, **kwargs):
    layout = DIFFICULTY_LAYOUTS[difficulty]
    payload = {
        "node": node,
        "difficulty": difficulty,
        "width": layout["width"],
        "height": layout["height"],
        "mine_count": layout["mine_count"],
    }
    payload.update(kwargs)
    return MinesweeperGame.objects.create(team=team, **payload)


class TestMinesweeperGameDefaults:
    def test_new_game_is_in_progress_with_empty_board(self, team, node):
        game = start_game(team, node)
        assert game.status == MinesweeperStatus.IN_PROGRESS
        assert game.score == 0
        assert game.finished_at is None
        assert game.started_at is not None
        assert game.node_id == node.pk
        assert game.board == {"cells": []}

    def test_game_can_exist_without_a_team(self, node):
        game = start_game(None, node)
        assert game.team_id is None
        assert game.status == MinesweeperStatus.IN_PROGRESS

    def test_team_can_be_assigned_later(self, team, node):
        game = start_game(None, node)
        game.team = team
        game.save(update_fields=["team"])
        game.refresh_from_db()
        assert game.team_id == team.pk

    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_legal_layouts_are_accepted(self, team, node, difficulty):
        game = start_game(team, node, difficulty)
        assert (game.width, game.height, game.mine_count) == (
            DIFFICULTY_LAYOUTS[difficulty]["width"],
            DIFFICULTY_LAYOUTS[difficulty]["height"],
            DIFFICULTY_LAYOUTS[difficulty]["mine_count"],
        )


class TestMinesweeperGameConstraints:
    def test_layout_must_match_difficulty(self, team, node):
        with pytest.raises(IntegrityError), transaction.atomic():
            start_game(team, node, width=16, height=16, mine_count=40)

    def test_in_progress_cannot_have_finished_at(self, team, node):
        with pytest.raises(IntegrityError), transaction.atomic():
            start_game(team, node, finished_at=timezone.now())

    def test_finished_game_requires_finished_at(self, team, node):
        with pytest.raises(IntegrityError), transaction.atomic():
            start_game(team, node, status=MinesweeperStatus.WON)

    def test_won_with_finished_at_is_accepted(self, team, node):
        game = start_game(
            team,
            node,
            status=MinesweeperStatus.WON,
            finished_at=timezone.now(),
        )
        assert game.finished_at is not None

    def test_negative_score_rejected(self, team, node):
        with pytest.raises(IntegrityError), transaction.atomic():
            start_game(team, node, score=-1)

    def test_team_delete_is_protected(self, team, node):
        start_game(team, node)
        with pytest.raises(ProtectedError), transaction.atomic():
            team.delete()

    def test_node_delete_is_protected(self, team, node):
        start_game(team, node)
        with pytest.raises(ProtectedError), transaction.atomic():
            node.delete()

    def test_node_is_required(self, team):
        layout = DIFFICULTY_LAYOUTS[MinesweeperDifficulty.EASY]
        with pytest.raises(IntegrityError), transaction.atomic():
            MinesweeperGame.objects.create(
                team=team,
                difficulty=MinesweeperDifficulty.EASY,
                width=layout["width"],
                height=layout["height"],
                mine_count=layout["mine_count"],
            )
