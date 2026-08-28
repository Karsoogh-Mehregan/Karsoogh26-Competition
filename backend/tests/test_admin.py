"""Every registered admin page loads, and the read-only guards actually hold."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model

from game.models import GameSettings, Occupancy

pytestmark = pytest.mark.django_db

REGISTERED = [(m._meta.app_label, m._meta.model_name) for m in admin.site._registry]


@pytest.fixture
def client_admin(client):
    user = get_user_model().objects.create_superuser("smoke", "s@example.com", "pw")
    client.force_login(user)
    return client


@pytest.mark.parametrize(("app_label", "model_name"), REGISTERED)
def test_changelist_loads(client_admin, app_label, model_name):
    response = client_admin.get(f"/admin/{app_label}/{model_name}/")
    assert response.status_code == 200


def test_occupancy_cannot_be_added_by_hand(client_admin):
    """Occupancies are written by the locked service path only."""
    assert admin.site._registry[Occupancy].has_add_permission(None) is False
    assert client_admin.get("/admin/game/occupancy/add/").status_code == 403


def test_occupancy_fields_are_readonly():
    readonly = admin.site._registry[Occupancy].readonly_fields
    for field in ("slot", "floor", "grade", "points", "release_reason"):
        assert field in readonly


def test_gamesettings_refuses_a_second_row(client_admin):
    game_admin = admin.site._registry[GameSettings]
    assert game_admin.has_add_permission(None) is True
    GameSettings.load()
    assert game_admin.has_add_permission(None) is False
    assert game_admin.has_delete_permission(None) is False
