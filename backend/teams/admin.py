from django.contrib import admin

from .models import BalanceEvent, Team, TeamItem


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "board", "color", "balance", "draft_order", "last_duel_at")
    list_filter = ("board",)
    search_fields = ("code", "name")
    ordering = ("draft_order",)


@admin.register(TeamItem)
class TeamItemAdmin(admin.ModelAdmin):
    list_display = ("team", "item_type", "quantity", "created_at")
    list_filter = ("item_type",)
    search_fields = ("team__code", "team__name")
    list_select_related = ("team",)
    ordering = ("team", "item_type")


@admin.register(BalanceEvent)
class BalanceEventAdmin(admin.ModelAdmin):
    list_display = ("team", "delta", "balance_after", "reason", "detail", "created_at")
    list_filter = ("reason",)
    search_fields = ("team__code", "team__name", "detail")
    ordering = ("-created_at", "-pk")
