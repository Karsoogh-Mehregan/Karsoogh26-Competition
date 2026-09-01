import pytest
from django.db import connection


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
