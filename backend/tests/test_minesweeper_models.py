"""Database invariants for MinesweeperGame and MinesweeperAttempt — not gameplay."""

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from game.models import LevelConfig, Node
from minesweeper.models import (
    DIFFICULTY_LAYOUTS,
    MinesweeperAttempt,
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
def other_team():
    return Team.objects.create(code="beta", name="Beta")


@pytest.fixture
def node():
    return Node.objects.create(
        code="ms1",
        name="MS 1",
        level=LevelConfig.objects.get(level="easy"),
    )


def start_game(node, difficulty=MinesweeperDifficulty.EASY, **kwargs):
    layout = DIFFICULTY_LAYOUTS[difficulty]
    payload = {
        "node": node,
        "difficulty": difficulty,
        "width": layout["width"],
        "height": layout["height"],
        "mine_count": layout["mine_count"],
    }
    payload.update(kwargs)
    return MinesweeperGame.objects.create(**payload)


def start_attempt(game, team, **kwargs):
    payload = {"game": game, "team": team}
    payload.update(kwargs)
    return MinesweeperAttempt.objects.create(**payload)


class TestMinesweeperGameDefaults:
    def test_new_game_has_empty_layout(self, node):
        game = start_game(node)
        assert game.node_id == node.pk
        assert game.board == {"cells": []}
        assert game.created_at is not None

    def test_game_has_no_team_field(self, node):
        game = start_game(node)
        field_names = {field.name for field in MinesweeperGame._meta.get_fields()}
        assert "team" not in field_names
        assert game.node_id == node.pk

    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_legal_layouts_are_accepted(self, node, difficulty):
        game = start_game(node, difficulty)
        assert (game.width, game.height, game.mine_count) == (
            DIFFICULTY_LAYOUTS[difficulty]["width"],
            DIFFICULTY_LAYOUTS[difficulty]["height"],
            DIFFICULTY_LAYOUTS[difficulty]["mine_count"],
        )


class TestMinesweeperGameConstraints:
    def test_layout_must_match_difficulty(self, node):
        with pytest.raises(IntegrityError), transaction.atomic():
            start_game(node, width=16, height=16, mine_count=40)

    def test_node_delete_is_protected(self, node):
        start_game(node)
        with pytest.raises(ProtectedError), transaction.atomic():
            node.delete()

    def test_node_is_required(self):
        layout = DIFFICULTY_LAYOUTS[MinesweeperDifficulty.EASY]
        with pytest.raises(IntegrityError), transaction.atomic():
            MinesweeperGame.objects.create(
                difficulty=MinesweeperDifficulty.EASY,
                width=layout["width"],
                height=layout["height"],
                mine_count=layout["mine_count"],
            )


class TestMinesweeperAttemptDefaults:
    def test_attempt_belongs_to_game_and_team(self, team, node):
        game = start_game(node)
        attempt = start_attempt(game, team)
        assert attempt.game_id == game.pk
        assert attempt.team_id == team.pk
        assert attempt.status == MinesweeperStatus.IN_PROGRESS
        assert attempt.score == 0
        assert attempt.finished_at is None
        assert attempt.started_at is not None
        assert attempt.board == {"cells": []}

    def test_multiple_historical_attempts_are_allowed(self, team, node):
        game = start_game(node)
        first = start_attempt(
            game,
            team,
            status=MinesweeperStatus.LOST,
            finished_at=timezone.now(),
        )
        second = start_attempt(game, team)
        assert first.pk != second.pk
        assert MinesweeperAttempt.objects.filter(game=game, team=team).count() == 2

    def test_multiple_finished_attempts_are_allowed(self, team, other_team, node):
        game = start_game(node)
        first = start_attempt(
            game,
            team,
            status=MinesweeperStatus.WON,
            finished_at=timezone.now(),
        )
        second = start_attempt(
            game,
            other_team,
            status=MinesweeperStatus.LOST,
            finished_at=timezone.now(),
        )
        assert first.pk != second.pk
        assert MinesweeperAttempt.objects.filter(game=game).count() == 2


class TestMinesweeperAttemptConstraints:
    def test_only_one_in_progress_attempt_per_game(self, team, other_team, node):
        game = start_game(node)
        start_attempt(game, team)
        with pytest.raises(IntegrityError), transaction.atomic():
            start_attempt(game, other_team)

    def test_in_progress_cannot_have_finished_at(self, team, node):
        game = start_game(node)
        with pytest.raises(IntegrityError), transaction.atomic():
            start_attempt(game, team, finished_at=timezone.now())

    def test_finished_attempt_requires_finished_at(self, team, node):
        game = start_game(node)
        with pytest.raises(IntegrityError), transaction.atomic():
            start_attempt(game, team, status=MinesweeperStatus.WON)

    def test_won_with_finished_at_is_accepted(self, team, node):
        game = start_game(node)
        attempt = start_attempt(
            game,
            team,
            status=MinesweeperStatus.WON,
            finished_at=timezone.now(),
        )
        assert attempt.finished_at is not None

    def test_negative_score_rejected(self, team, node):
        game = start_game(node)
        with pytest.raises(IntegrityError), transaction.atomic():
            start_attempt(game, team, score=-1)

    def test_team_delete_is_protected(self, team, node):
        game = start_game(node)
        start_attempt(game, team)
        with pytest.raises(ProtectedError), transaction.atomic():
            team.delete()

    def test_deleting_game_cascades_attempts(self, team, node):
        game = start_game(node)
        start_attempt(game, team)
        game.delete()
        assert not MinesweeperAttempt.objects.exists()
