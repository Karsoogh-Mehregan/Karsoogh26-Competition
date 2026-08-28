"""Races for the last free unit of a house.

Marked postgres_only and skipped elsewhere rather than allowed to pass: on
SQLite select_for_update() is silently ignored (has_select_for_update = False,
never overridden by the sqlite3 backend), so a green run here would be
meaningless.
"""

import importlib
import threading

import pytest
from django.apps import apps as global_apps
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from game.models import GameSettings, GameStatus, LevelConfig, Node, Occupancy
from game.services import grade_attempt
from teams.models import Team

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres_only]

THREADS = 8


def reseed_economy():
    """TransactionTestCase flushes the database, migration-seeded rows included.

    Re-run the seed rather than restating its numbers here, so the economy stays
    defined in exactly one place.
    """
    importlib.import_module("game.migrations.0002_seed_economy").seed(global_apps, None)


def test_only_one_team_wins_the_last_slot():
    easy = LevelConfig.objects.get(level="easy")  # capacity 1
    node = Node.objects.create(code="e1", name="Easy 1", level=easy)
    teams = [Team.objects.create(code=f"r{i}", name=f"Racer {i}") for i in range(THREADS)]

    barrier = threading.Barrier(THREADS)
    winners, losers = [], []
    lock = threading.Lock()

    def claim(team):
        barrier.wait()  # maximise the overlap
        try:
            with transaction.atomic():
                Occupancy.objects.create(node=node, team=team, slot=1)
            with lock:
                winners.append(team.code)
        except IntegrityError:
            with lock:
                losers.append(team.code)
        finally:
            connection.close()

    threads = [threading.Thread(target=claim, args=(t,)) for t in teams]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1, f"expected exactly one winner, got {winners}"
    assert len(losers) == THREADS - 1
    assert Occupancy.objects.active().filter(node=node).count() == 1


def test_simultaneous_grades_build_one_consistent_tower():
    """Two mentors judging the same house at once.

    grade_attempt re-ranks every active row on the node, so the two calls must
    serialise on the same lock. If they did not, both would compute floors from the
    same pre-state and collide on occ_one_team_per_floor -- or, worse, overwrite each
    other and pay twice.
    """
    reseed_economy()
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])

    medium = LevelConfig.objects.get(level="medium")  # capacity 2, floors 200 / 250
    node = Node.objects.create(code="m1", name="Medium 1", level=medium)
    assigned = timezone.now()
    judged = [("top", 100), ("bottom", 60)]
    for slot, (code, _) in enumerate(judged, start=1):
        Occupancy.objects.create(
            node=node,
            team=Team.objects.create(code=code, name=code),
            slot=slot,
            question_assigned_at=assigned,
        )

    barrier = threading.Barrier(len(judged))
    errors = []

    def judge(code, grade):
        barrier.wait()
        try:
            grade_attempt(
                Occupancy.objects.active()
                .select_related("node", "node__level", "team")
                .get(node=node, team__code=code),
                grade,
            )
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            errors.append(f"{code}: {exc!r}")
        finally:
            connection.close()

    threads = [threading.Thread(target=judge, args=pair) for pair in judged]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, errors

    # Whichever order the two land in, the outcome is the same: the tower is packed
    # 1..2 with the better grade on top, and each team is paid exactly once.
    assert sorted(Occupancy.objects.active().filter(node=node).values_list("floor", flat=True)) == [
        1,
        2,
    ]
    assert dict(Team.objects.values_list("code", "balance")) == {
        "top": 250,  # 250 * 1.000
        "bottom": 100,  # 200 * 0.500
    }
