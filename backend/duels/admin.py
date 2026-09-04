"""Admin for the rooms organisers create and the duels the game produces.

Rooms are the only thing here that is meant to be typed in by hand — «the admin
should have access to making rooms for mentors, assigning the mentor and the
link». Duels are read-mostly: they are opened by players and closed by judges,
and the admin exists so an organiser can see the queue and unstick a duel whose
judge went home.
"""

from django import forms
from django.contrib import admin

from notifications.services import users_with_perm

from .models import Duel, DuelStatus, Room
from .permissions import JUDGE_PERM


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """Offer only actual judges.

        By explicit grant, not `has_perm` — otherwise every superuser would be
        listed as a candidate judge, and the queue would hand duels to people
        who are not in the building. Same reasoning as the audience scopes.
        """
        super().__init__(*args, **kwargs)
        mentor = self.fields.get("mentor")
        if mentor is not None:
            mentor.queryset = users_with_perm(JUDGE_PERM).filter(is_active=True)
            mentor.help_text = "Only users holding judge_duel (the DuelMentors group)."


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    form = RoomForm
    list_display = ("name", "mentor", "is_active", "duels_hosted", "last_assigned_at")
    list_filter = ("is_active",)
    search_fields = ("name", "link", "mentor__username")
    list_select_related = ("mentor",)
    readonly_fields = ("created_at",)
    actions = ["reset_rotation"]

    @admin.display(description="duels")
    def duels_hosted(self, room: Room) -> int:
        return room.duels.count()

    @admin.action(description="Send to the front of the rotation")
    def reset_rotation(self, request, queryset):
        """Clear `last_assigned_at`, which the queue reads as never-used."""
        updated = queryset.update(last_assigned_at=None)
        self.message_user(request, f"{updated} room(s) moved to the front of the queue.")


@admin.register(Duel)
class DuelAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "attacker",
        "attacked",
        "node",
        "floor",
        "stake",
        "status",
        "winner",
        "mentor",
        "created_at",
    )
    list_filter = ("status", "node__level")
    search_fields = ("attacker__name", "attacked__name", "node__code")
    list_select_related = ("attacker", "attacked", "node", "winner", "mentor")
    autocomplete_fields = ("attacker", "attacked", "winner", "loser", "target")
    readonly_fields = ("created_at", "resolved_at", "stake", "floor")

    def has_add_permission(self, request):
        """Duels are opened by players paying for them, never typed in."""
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.status == DuelStatus.CLOSED:
            # A settled duel already moved money and a floor. Editing the result
            # here would not undo either, so the row is frozen.
            return [field.name for field in self.model._meta.fields]
        return self.readonly_fields
