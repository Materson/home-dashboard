from __future__ import annotations

from django.contrib import admin

from .models import Attachment


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "original_name", "mime_type", "size_bytes", "created_at")
    search_fields = ("original_name", "sha256")
    date_hierarchy = "created_at"
    readonly_fields = ("sha256", "size_bytes", "mime_type")
