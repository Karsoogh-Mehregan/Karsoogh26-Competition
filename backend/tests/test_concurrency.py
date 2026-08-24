"""Races for the last free unit of a house.

Marked postgres_only and skipped elsewhere rather than allowed to pass: on
SQLite select_for_update() is silently ignored (has_select_for_update = False,
never overridden by the sqlite3 backend), so a green run here would be
meaningless.
"""

import threading

import pytest
from django.db import IntegrityError, connection, transaction

from game.models import LevelConfig, Node, Occupancy
from teams.models import Team

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres_only]

THREADS = 8


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
