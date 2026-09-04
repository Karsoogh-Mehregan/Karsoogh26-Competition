import importlib

import pytest
from django.apps import apps as global_apps
from django.db import connection

# Migrations whose RunPython writes rows the tests read back. Re-run rather than
# restated here, so the economy stays defined in exactly one place.
_SEED_MIGRATIONS = (
    "game.migrations.0002_seed_economy",
    "game.migrations.0007_seed_toll_level",
)


@pytest.fixture(autouse=True)
def _reseed_after_flush(request):
    """Put the migration-seeded rows back for a `transaction=True` test.

    TransactionTestCase truncates every table at teardown, migration-seeded rows
    included, so the *next* transactional test starts on a database with no
    LevelConfig and no GradeMultiplier. The first one in a session gets away with
    it, which is exactly the kind of order-dependent green that hides until a new
    test file lands after this one.

    Only the economy is restored. A transactional test that needs the group or
    map-design seeds should add its migration to `_SEED_MIGRATIONS`.
    """
    marker = request.node.get_closest_marker("django_db")
    if not (marker and marker.kwargs.get("transaction")):
        return
    if connection.vendor != "postgresql" and request.node.get_closest_marker("postgres_only"):
        return
    request.getfixturevalue("transactional_db")
    for name in _SEED_MIGRATIONS:
        importlib.import_module(name).seed(global_apps, None)


@pytest.fixture(autouse=True)
def _skip_postgres_only(request):
    """Skip — never silently pass — PostgreSQL-only tests on SQLite.

    select_for_update() is not merely unsupported on SQLite, it is silently
    ignored, so a concurrency test would report a false pass.
    """
    if request.node.get_closest_marker("postgres_only") and connection.vendor != "postgresql":
        pytest.skip(f"needs PostgreSQL, running on {connection.vendor}")


@pytest.fixture(autouse=True)
def _no_ssl_redirect(settings):
    """The test client speaks plain HTTP; SECURE_SSL_REDIRECT would 301 every request."""
    settings.SECURE_SSL_REDIRECT = False
