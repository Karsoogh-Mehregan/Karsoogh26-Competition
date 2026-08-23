from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (*BaseUserAdmin.list_display, "team")
    list_filter = (*BaseUserAdmin.list_filter, "team")
    autocomplete_fields = ("team",)
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        ("Competition", {"fields": ("team",)}),
    )
    add_fieldsets = (
        *BaseUserAdmin.add_fieldsets,
        ("Competition", {"fields": ("team",)}),
    )
