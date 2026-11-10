from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import Group

from .models import AccessGrant


@admin.register(AccessGrant)
class AccessGrantAdmin(admin.ModelAdmin):
    list_display = ("module", "level", "effect", "user", "group", "subjects", "valid_until")
    list_filter = ("module", "level", "effect", "subjects")
    search_fields = ("user__email", "group__name")
    autocomplete_fields = ("user", "group")


class AccessGrantInline(admin.TabularInline):
    """Edit a group's AccessGrants directly from the Group admin page.

    Only group-scoped grants show here; user-scoped grants live on each User."""

    model = AccessGrant
    fk_name = "group"
    extra = 0
    fields = (
        "module",
        "level",
        "effect",
        "subjects",
        "person_ids",
        "data_from",
        "data_to",
        "valid_until",
    )
    verbose_name = "Access grant"
    verbose_name_plural = "Access grants"


class GroupAdmin(DjangoGroupAdmin):
    inlines = (AccessGrantInline,)


# Replace the stock Group admin with the one that shows our grants inline.
admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)
