"""Health: per-person medical history, medications (with dose reminders),
medicine purchases, appointments and test results.

Every record belongs to a ``Person`` — access is scoped by person (a child
sees only their own) and by the grant's date window. ``_access_person_field``
/ ``_access_date_field`` tell ``AccessContext.require`` how to check a single
object (used for attachments and edits).

Reminder texts are Polish and *generic* ("Pora na lek") — health details
never go into e-mail or lock-screen notifications.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.core.models import TimeStamped, UUIDModel, currency_field, money_amount_field


class _PersonRecord(UUIDModel, TimeStamped):
    person = models.ForeignKey("people.Person", on_delete=models.CASCADE, related_name="+")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    _access_person_field = "person"

    class Meta:
        abstract = True


class Condition(_PersonRecord):
    """An illness, injury, allergy, chronic condition, vaccination…"""

    class Kind(models.TextChoices):
        ILLNESS = "illness", "Illness"
        INJURY = "injury", "Injury"
        CHRONIC = "chronic", "Chronic condition"
        ALLERGY = "allergy", "Allergy"
        VACCINATION = "vaccination", "Vaccination"
        OTHER = "other", "Other"

    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.ILLNESS)
    title = models.CharField(max_length=200)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True)
    doctor = models.CharField(max_length=120, blank=True)

    _access_date_field = "start_date"

    class Meta:
        ordering = ("-start_date", "-created_at")


class Medication(_PersonRecord):
    """A course of a medicine. With ``dose_times`` and reminders on, a dose
    log entry + reminder is created for every dose (see ``doses.py``)."""

    name = models.CharField(max_length=120)
    dosage = models.CharField(max_length=120, blank=True, help_text="e.g. '1 tabletka', '5 ml'")
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, help_text="Empty = ongoing.")
    # Local times of day, "HH:MM", e.g. ["08:00", "16:00", "23:59"].
    dose_times = models.JSONField(default=list, blank=True)
    reminders_enabled = models.BooleanField(default=True)
    condition = models.ForeignKey(
        Condition, null=True, blank=True, on_delete=models.SET_NULL, related_name="medications"
    )

    _access_date_field = "start_date"

    class Meta:
        ordering = ("-start_date", "name")

    def __str__(self) -> str:
        return self.name


class DoseLog(UUIDModel, TimeStamped):
    """One scheduled dose and whether it was taken."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        TAKEN = "taken", "Taken"
        SKIPPED = "skipped", "Skipped"

    medication = models.ForeignKey(Medication, on_delete=models.CASCADE, related_name="doses")
    scheduled_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    status_at = models.DateTimeField(null=True, blank=True)

    # Checked through the medication's person (see ``person_id`` below).
    _access_person_field = "person"

    class Meta:
        ordering = ("scheduled_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["medication", "scheduled_at"], name="health_dose_unique"
            ),
        ]

    @property
    def person_id(self):
        return self.medication.person_id


class MedicinePurchase(_PersonRecord):
    """Buying medicine — the cost goes to Finance (health.medicines)."""

    date = models.DateField(db_index=True)
    name = models.CharField(max_length=200, help_text="What was bought.")
    medication = models.ForeignKey(
        Medication, null=True, blank=True, on_delete=models.SET_NULL, related_name="purchases"
    )
    cost = money_amount_field()
    currency = currency_field()
    pharmacy = models.CharField(max_length=120, blank=True)

    _access_date_field = "date"

    class Meta:
        ordering = ("-date", "-created_at")


class Appointment(_PersonRecord):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    starts_at = models.DateTimeField(db_index=True)
    doctor = models.CharField(max_length=120, blank=True)
    specialty = models.CharField(max_length=120, blank=True)
    place = models.CharField(max_length=200, blank=True)
    purpose = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    cost = money_amount_field(null=True, blank=True)
    currency = currency_field()

    _access_date_field = "starts_at"

    class Meta:
        ordering = ("-starts_at",)


class TestResult(_PersonRecord):
    """Lab work / imaging. The document is an attachment (core.Attachment);
    reading values out of it comes with the AI assistant (M6)."""

    __test__ = False  # not a pytest test class, despite the name

    date = models.DateField(db_index=True)
    title = models.CharField(max_length=200)
    lab = models.CharField(max_length=120, blank=True)

    _access_date_field = "date"

    class Meta:
        ordering = ("-date", "-created_at")
