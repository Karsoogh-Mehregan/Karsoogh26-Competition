from django.contrib import admin

from .models import BalanceEvent, Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "color", "balance", "draft_order", "last_duel_at")
    search_fields = ("code", "name")
    ordering = ("draft_order",)


@admin.register(BalanceEvent)
class BalanceEventAdmin(admin.ModelAdmin):
    list_display = ("team", "delta", "balance_after", "reason", "detail", "created_at")
    list_filter = ("reason",)
    search_fields = ("team__code", "team__name", "detail")
    ordering = ("-created_at", "-pk")
