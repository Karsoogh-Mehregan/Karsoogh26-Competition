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
    search_fields = ("team__code", "detail")
    list_select_related = ("team",)
    readonly_fields = ("team", "delta", "balance_after", "reason", "detail", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
