"""Database invariants for MinesweeperSettings, MinesweeperGame, and MinesweeperAttempt."""

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from core.boards import Board
from game.models import LevelConfig, Node
from minesweeper.models import (
    DifficultyConfig,
    MinesweeperAttempt,
    MinesweeperDifficulty,
    MinesweeperGame,
    MinesweeperSettings,
    MinesweeperStatus,
)
from teams.models import Team

pytestmark = pytest.mark.django_db


@pytest.fixture
def team():
    return Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha")


@pytest.fixture
def other_team():
    return Team.objects.create(board=Board.GIRLS, code="beta", name="Beta")


@pytest.fixture
def node():
    return Node.objects.create(
        board=Board.GIRLS,
        code="ms1",
        name="MS 1",
        level=LevelConfig.objects.get(level="easy"),
    )


def layout_for(difficulty=MinesweeperDifficulty.EASY) -> DifficultyConfig:
    """The seeded config row. Difficulties are data now, not constants."""
    return DifficultyConfig.objects.get(pk=difficulty)


def start_settings(node, difficulty=MinesweeperDifficulty.HARD, *, enabled=True):
    return MinesweeperSettings.objects.create(
        node=node,
        difficulty_id=difficulty,
        enabled=enabled,
    )


def start_game(node, difficulty=MinesweeperDifficulty.EASY, **kwargs):
    layout = layout_for(difficulty)
    payload = {
        "node": node,
        "difficulty": layout,
        "width": layout.width,
        "height": layout.height,
        "mine_count": layout.mine_count,
        "base_score": layout.base_score,
    }
    payload.update(kwargs)
    return MinesweeperGame.objects.create(**payload)


def start_attempt(game, team, **kwargs):
    payload = {"game": game, "team": team}
    payload.update(kwargs)
    return MinesweeperAttempt.objects.create(**payload)


class TestMinesweeperSettings:
    def test_node_can_have_settings(self, node):
        settings = start_settings(node, MinesweeperDifficulty.HARD)
        assert settings.node_id == node.pk
        assert settings.difficulty_id == MinesweeperDifficulty.HARD
        assert settings.enabled is True
        assert node.minesweeper_settings.pk == settings.pk
        assert settings.created_at is not None
        assert settings.updated_at is not None

    def test_difficulty_is_stored(self, node):
        settings = start_settings(node, MinesweeperDifficulty.MEDIUM)
        stored = MinesweeperSettings.objects.get(pk=settings.pk)
        assert stored.difficulty_id == MinesweeperDifficulty.MEDIUM
        assert stored.difficulty.width == 16

    def test_one_settings_row_per_node(self, node):
        start_settings(node)
        with pytest.raises(IntegrityError), transaction.atomic():
            start_settings(node, MinesweeperDifficulty.EASY)

    def test_settings_have_no_board_or_team(self, node):
        settings = start_settings(node)
        field_names = {field.name for field in MinesweeperSettings._meta.get_fields()}
        assert "board" not in field_names
        assert "team" not in field_names
        assert "status" not in field_names
        assert "score" not in field_names
        assert settings.node_id == node.pk

    def test_deleting_node_cascades_settings(self, node):
        start_settings(node)
        node.delete()
        assert not MinesweeperSettings.objects.exists()


class TestMinesweeperGameDefaults:
    def test_new_game_has_empty_layout(self, node):
        game = start_game(node)
        assert game.node_id == node.pk
        assert game.board == {"cells": []}
        assert game.created_at is not None

    def test_game_has_no_team_status_or_score(self, node):
        game = start_game(node)
        field_names = {field.name for field in MinesweeperGame._meta.get_fields()}
        assert "team" not in field_names
        assert "status" not in field_names
        assert "score" not in field_names
        assert "finished_at" not in field_names
        assert game.node_id == node.pk

    @pytest.mark.parametrize("difficulty", list(MinesweeperDifficulty))
    def test_legal_layouts_are_accepted(self, node, difficulty):
        game = start_game(node, difficulty)
        layout = layout_for(difficulty)
        assert (game.width, game.height, game.mine_count) == (
            layout.width,
            layout.height,
            layout.mine_count,
        )

    def test_board_keeps_its_own_layout_when_the_difficulty_is_retuned(self, node):
        game = start_game(node, MinesweeperDifficulty.EASY)
        config = layout_for(MinesweeperDifficulty.EASY)
        config.width, config.height, config.mine_count, config.base_score = 12, 12, 20, 999
        config.save()

        game.refresh_from_db()
        assert (game.width, game.height, game.mine_count) == (9, 9, 10)
        assert game.base_score == 100


class TestMinesweeperGameConstraints:
    def test_node_delete_is_protected(self, node):
        start_game(node)
        with pytest.raises(ProtectedError), transaction.atomic():
            node.delete()

    def test_difficulty_delete_is_protected(self, node):
        start_game(node, MinesweeperDifficulty.EASY)
        with pytest.raises(ProtectedError), transaction.atomic():
            layout_for(MinesweeperDifficulty.EASY).delete()

    def test_node_is_required(self):
        layout = layout_for(MinesweeperDifficulty.EASY)
        with pytest.raises(IntegrityError), transaction.atomic():
            MinesweeperGame.objects.create(
                difficulty=layout,
                width=layout.width,
                height=layout.height,
                mine_count=layout.mine_count,
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

    def test_two_in_progress_attempts_on_different_games(self, team, other_team, node):
        first_game = start_game(node)
        second_game = start_game(node)
        first = start_attempt(first_game, team)
        second = start_attempt(second_game, other_team)
        assert first.game_id != second.game_id
        assert first.status == MinesweeperStatus.IN_PROGRESS
        assert second.status == MinesweeperStatus.IN_PROGRESS

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
