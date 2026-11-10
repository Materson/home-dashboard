"""Symptoms become dated entries of an illness/event (to follow how they
change) instead of a plain list on the event. Existing list items become
entries at noon of the event's start date; the reverse folds them back."""

from __future__ import annotations

from datetime import datetime, time

import apps.core.uuid7
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def list_to_entries(apps, schema_editor):
    Condition = apps.get_model("health", "Condition")
    Symptom = apps.get_model("health", "Symptom")
    for c in Condition.objects.all():
        if not c.symptoms:
            continue
        at = timezone.make_aware(datetime.combine(c.start_date, time(12, 0)))
        for name in c.symptoms:
            Symptom.objects.create(
                person_id=c.person_id,
                condition=c,
                observed_at=at,
                symptom=name,
                created_by_id=c.created_by_id,
            )


def entries_to_list(apps, schema_editor):
    Condition = apps.get_model("health", "Condition")
    Symptom = apps.get_model("health", "Symptom")
    for c in Condition.objects.all():
        names: list[str] = []
        for s in Symptom.objects.filter(condition=c).order_by("observed_at"):
            if s.symptom.lower() not in {n.lower() for n in names}:
                names.append(s.symptom)
        if names:
            c.symptoms = names
            c.save(update_fields=["symptoms"])


class Migration(migrations.Migration):
    dependencies = [
        ("health", "0007_condition_symptoms_drop_doctor"),
        ("people", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Symptom",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid7.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("notes", models.TextField(blank=True)),
                ("observed_at", models.DateTimeField(db_index=True)),
                ("symptom", models.CharField(max_length=80)),
                (
                    "severity",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("mild", "Mild"),
                            ("moderate", "Moderate"),
                            ("severe", "Severe"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "value",
                    models.CharField(blank=True, help_text="e.g. '38,5 °C'", max_length=40),
                ),
                (
                    "condition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="symptom_log",
                        to="health.condition",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="people.person",
                    ),
                ),
            ],
            options={
                "ordering": ("-observed_at", "-created_at"),
            },
        ),
        migrations.RunPython(list_to_entries, entries_to_list),
        migrations.RemoveField(model_name="condition", name="symptoms"),
    ]
