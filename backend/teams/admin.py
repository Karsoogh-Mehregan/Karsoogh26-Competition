from django.contrib import admin

from .models import Team


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "color", "balance", "draft_order", "last_duel_at")
    search_fields = ("code", "name")
    ordering = ("draft_order",)
