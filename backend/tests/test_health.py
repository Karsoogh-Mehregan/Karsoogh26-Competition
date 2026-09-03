"""The container healthcheck's contract: reachable over plain HTTP, no I/O.

Neither test takes a database fixture on purpose — pytest-django raises on any
query, so passing without `django_db` is the proof that /healthz stays liveness
only and cannot be dragged down by a database blip.
"""

from django.urls import reverse


def test_healthz_is_open_and_touches_no_database(client):
    response = client.get(reverse("healthz"))

    assert response.status_code == 200
    assert response.content == b"ok"


def test_healthz_is_exempt_from_the_ssl_redirect(client, settings):
    """SECURE_SSL_REDIRECT is on in production; a 301 would read as unhealthy."""
    settings.SECURE_SSL_REDIRECT = True

    assert client.get("/healthz").status_code == 200
    # Scoped, not global.
    assert client.get("/api/teams/").status_code == 301
