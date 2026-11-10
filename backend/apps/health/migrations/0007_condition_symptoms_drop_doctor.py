"""Health events: add a symptom list; drop the doctor field (doctors belong
to visits). An existing doctor is kept as a "Lekarz: …" line in the notes,
and the reverse moves that line back."""

from __future__ import annotations

from django.db import migrations, models

PREFIX = "Lekarz: "


def doctor_to_notes(apps, schema_editor):
    Condition = apps.get_model("health", "Condition")
    for c in Condition.objects.exclude(doctor=""):
        line = f"{PREFIX}{c.doctor}"
        c.notes = f"{line}\n{c.notes}" if c.notes else line
        c.save(update_fields=["notes"])


def notes_to_doctor(apps, schema_editor):
    Condition = apps.get_model("health", "Condition")
    for c in Condition.objects.filter(notes__startswith=PREFIX):
        first, _, rest = c.notes.partition("\n")
        c.doctor = first[len(PREFIX) :][:120]
        c.notes = rest
        c.save(update_fields=["doctor", "notes"])


class Migration(migrations.Migration):
    dependencies = [("health", "0006_link_events_cabinet_and_finance")]

    operations = [
        migrations.AddField(
            model_name="condition",
            name="symptoms",
            field=models.JSONField(
                blank=True, default=list, help_text='e.g. ["gorączka", "kaszel"]'
            ),
        ),
        migrations.RunPython(doctor_to_notes, notes_to_doctor),
        migrations.RemoveField(model_name="condition", name="doctor"),
    ]
