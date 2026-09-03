from django import forms
from django.contrib import admin

from .models import MinesweeperGame
from .services import assign_game_to_team, create_game


class MinesweeperGameAddForm(forms.ModelForm):
    class Meta:
        model = MinesweeperGame
        fields = ("node", "difficulty", "team")


@admin.register(MinesweeperGame)
class MinesweeperGameAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "team",
        "node",
        "difficulty",
        "status",
        "score",
        "width",
        "height",
        "mine_count",
        "started_at",
        "finished_at",
    )
    list_filter = ("difficulty", "status")
    search_fields = ("team__code", "team__name", "node__code", "node__name")
    list_select_related = ("team", "node")
    autocomplete_fields = ("team", "node")
    ordering = ("-started_at",)

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = MinesweeperGameAddForm
        return super().get_form(request, obj, change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("node", "difficulty", "team")
        return (
            "node",
            "difficulty",
            "team",
            "status",
            "score",
            "width",
            "height",
            "mine_count",
            "board",
            "started_at",
            "finished_at",
            "created_at",
        )

    def get_readonly_fields(self, request, obj=None):
        timestamps = ("started_at", "finished_at", "created_at")
        if obj is None:
            return timestamps
        return timestamps + (
            "node",
            "difficulty",
            "width",
            "height",
            "mine_count",
            "board",
        )

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        created = create_game(obj.node, obj.difficulty)
        if obj.team_id:
            created = assign_game_to_team(created.pk, obj.team)
        obj.pk = created.pk
        obj.id = created.pk
        for field in (
            "team_id",
            "status",
            "score",
            "width",
            "height",
            "mine_count",
            "board",
            "started_at",
            "finished_at",
            "created_at",
        ):
            setattr(obj, field, getattr(created, field))
