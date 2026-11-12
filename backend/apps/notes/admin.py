from __future__ import annotations

from django.contrib import admin

from .models import Note, NoteShare


class ShareInline(admin.TabularInline):
    model = NoteShare
    extra = 0


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    # Private content: the admin lists notes but shows no text.
    list_display = ("id", "owner", "remind_at", "repeat", "archived_at", "updated_at")
    list_filter = ("repeat",)
    fields = ("owner", "remind_at", "repeat", "pinned", "archived_at")
    readonly_fields = ("owner",)
    inlines = (ShareInline,)
