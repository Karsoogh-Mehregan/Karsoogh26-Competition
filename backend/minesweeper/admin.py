from django import forms
from django.contrib import admin

from .models import MinesweeperAttempt, MinesweeperGame
from .services import create_game


class MinesweeperGameAddForm(forms.ModelForm):
    class Meta:
        model = MinesweeperGame
        fields = ("node", "difficulty")


class MinesweeperAttemptInline(admin.TabularInline):
    model = MinesweeperAttempt
    extra = 0
    can_delete = False
    autocomplete_fields = ("team",)
    readonly_fields = (
        "team",
        "status",
        "score",
        "board",
        "started_at",
        "finished_at",
        "created_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MinesweeperGame)
class MinesweeperGameAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "node",
        "difficulty",
        "width",
        "height",
        "mine_count",
        "created_at",
    )
    list_filter = ("difficulty",)
    search_fields = ("id", "node__code", "node__name")
    list_select_related = ("node",)
    autocomplete_fields = ("node",)
    ordering = ("-created_at",)
    inlines = (MinesweeperAttemptInline,)

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = MinesweeperGameAddForm
        return super().get_form(request, obj, change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("node", "difficulty")
        return (
            "node",
            "difficulty",
            "width",
            "height",
            "mine_count",
            "board",
            "created_at",
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return (
            "node",
            "difficulty",
            "width",
            "height",
            "mine_count",
            "board",
            "created_at",
        )

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        created = create_game(obj.node, obj.difficulty)
        obj.pk = created.pk
        obj.id = created.pk
        for field in ("width", "height", "mine_count", "board", "created_at"):
            setattr(obj, field, getattr(created, field))


@admin.register(MinesweeperAttempt)
class MinesweeperAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "game",
        "team",
        "status",
        "score",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "game__difficulty")
    search_fields = ("team__code", "team__name", "game__node__code")
    list_select_related = ("game", "game__node", "team")
    autocomplete_fields = ("game", "team")
    readonly_fields = ("started_at", "finished_at", "created_at", "board")
    ordering = ("-started_at",)
