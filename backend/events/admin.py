from django.contrib import admin

from .models import (
    CharityBagEvent,
    CharityBagParticipation,
    TerritoryCell,
    TerritoryGame,
    TerritoryTurn,
)


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


class CharityBagParticipationInline(admin.TabularInline):
    model = CharityBagParticipation
    extra = 0
    readonly_fields = (
        "team",
        "action",
        "amount",
        "stake_deducted",
        "final_payout",
        "submitted_at",
        "settled_at",
    )


@admin.register(CharityBagEvent)
class CharityBagEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "starts_at",
        "ends_at",
        "total_contributed",
        "total_requested",
        "charity_succeeded",
    )
    list_filter = ("status", "charity_succeeded")
    inlines = (CharityBagParticipationInline,)


@admin.register(CharityBagParticipation)
class CharityBagParticipationAdmin(admin.ModelAdmin):
    list_display = ("event", "team", "action", "amount", "final_payout", "submitted_at")
    list_filter = ("action",)
