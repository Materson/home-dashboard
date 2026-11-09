from __future__ import annotations

from django.contrib import admin

from .models import Category, Loan, Overpayment, RateChange, RecurringRule, Transaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "kind", "parent", "is_system")
    list_filter = ("kind", "is_system")
    search_fields = ("name", "key")
    autocomplete_fields = ("parent",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "name", "amount", "currency", "category", "person")
    list_filter = ("currency", "category", "person")
    search_fields = ("name", "notes")
    date_hierarchy = "date"
    autocomplete_fields = ("category", "person", "recurring_rule")


@admin.register(RecurringRule)
class RecurringRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "currency", "rrule", "next_run_at", "is_active")
    list_filter = ("is_active", "currency", "category")
    search_fields = ("name", "notes")


class RateChangeInline(admin.TabularInline):
    model = RateChange
    extra = 0


class OverpaymentInline(admin.TabularInline):
    model = Overpayment
    extra = 0


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("name", "principal", "currency", "start_date", "term_months", "base_rate")
    search_fields = ("name", "notes")
    inlines = (RateChangeInline, OverpaymentInline)
