"""Database invariants for MinesweeperGame — not gameplay."""

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

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


def start_game(team, difficulty=MinesweeperDifficulty.EASY, **kwargs):
    layout = DIFFICULTY_LAYOUTS[difficulty]
    payload = {
        "difficulty": difficulty,
        "width": layout["width"],
        "height": layout["height"],
        "mine_count": layout["mine_count"],
    }
    payload.update(kwargs)
    return MinesweeperGame.objects.create(team=team, **payload)


class TestMinesweeperGameDefaults:
    def test_new_game_is_in_progress_with_empty_board(self, team):
        game = start_game(team)
        assert game.status == MinesweeperStatus.IN_PROGRESS
        assert game.score == 0
        assert game.finished_at is None
        assert game.started_at is not None
        assert game.board == {"cells": []}

    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_legal_layouts_are_accepted(self, team, difficulty):
        game = start_game(team, difficulty)
        assert (game.width, game.height, game.mine_count) == (
            DIFFICULTY_LAYOUTS[difficulty]["width"],
            DIFFICULTY_LAYOUTS[difficulty]["height"],
            DIFFICULTY_LAYOUTS[difficulty]["mine_count"],
        )


class TestMinesweeperGameConstraints:
    def test_layout_must_match_difficulty(self, team):
        with pytest.raises(IntegrityError), transaction.atomic():
            start_game(team, width=16, height=16, mine_count=40)

    def test_in_progress_cannot_have_finished_at(self, team):
        with pytest.raises(IntegrityError), transaction.atomic():
            start_game(team, finished_at=timezone.now())

    def test_finished_game_requires_finished_at(self, team):
        with pytest.raises(IntegrityError), transaction.atomic():
            start_game(team, status=MinesweeperStatus.WON)

    def test_won_with_finished_at_is_accepted(self, team):
        game = start_game(
            team,
            status=MinesweeperStatus.WON,
            finished_at=timezone.now(),
        )
        assert game.finished_at is not None

    def test_negative_score_rejected(self, team):
        with pytest.raises(IntegrityError), transaction.atomic():
            start_game(team, score=-1)

    def test_team_delete_is_protected(self, team):
        start_game(team)
        with pytest.raises(ProtectedError), transaction.atomic():
            team.delete()
