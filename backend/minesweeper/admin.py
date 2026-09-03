from django.contrib import admin

from .models import MinesweeperGame


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
    readonly_fields = ("created_at", "started_at")
    ordering = ("-started_at",)
