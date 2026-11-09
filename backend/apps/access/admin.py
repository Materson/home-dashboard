from __future__ import annotations

from django.contrib import admin

from .models import AccessGrant


@admin.register(AccessGrant)
class AccessGrantAdmin(admin.ModelAdmin):
    list_display = ("module", "level", "effect", "user", "group", "subjects", "valid_until")
    list_filter = ("module", "level", "effect", "subjects")
    search_fields = ("user__email", "group__name")
    autocomplete_fields = ("user", "group")
