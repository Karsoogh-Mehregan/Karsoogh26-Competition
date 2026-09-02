from django.contrib import admin

from .models import MinesweeperGame


@admin.register(MinesweeperGame)
class MinesweeperGameAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "team",
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
    search_fields = ("team__code", "team__name")
    list_select_related = ("team",)
    autocomplete_fields = ("team",)
    readonly_fields = ("created_at", "started_at")
    ordering = ("-started_at",)
