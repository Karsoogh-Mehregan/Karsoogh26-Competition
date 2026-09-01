from django.contrib import admin

from .models import TerritoryCell, TerritoryGame, TerritoryTurn


class TerritoryCellInline(admin.TabularInline):
    model = TerritoryCell
    extra = 0
    max_num = 25
    readonly_fields = ("row", "column", "value", "owner")


@admin.register(TerritoryGame)
class TerritoryGameAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "player_one",
        "player_two",
        "active_player",
        "turns_completed",
        "status",
        "winner",
    )
    list_filter = ("status",)
    inlines = (TerritoryCellInline,)


@admin.register(TerritoryTurn)
class TerritoryTurnAdmin(admin.ModelAdmin):
    list_display = ("game", "number", "acting_player", "action_type", "success", "dice_result")
    list_filter = ("action_type", "success")
