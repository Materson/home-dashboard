from __future__ import annotations

from django.contrib import admin

from .models import Person


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("display_name", "birth_date", "user", "archived_at")
    search_fields = ("display_name",)
    list_filter = ("archived_at",)
    autocomplete_fields = ("user",)
