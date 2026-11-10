"""Health: per-person medical history, medications (with dose reminders),
appointments and test results; the household medicine cabinet.

An illness/event (``Condition``) is the hub: visits and treatments can point
at it. Treatments use a medicine from the cabinet. Buying medicine is a
Finance transaction linked to the cabinet item (``related_kind``).

Every record belongs to a ``Person`` — access is scoped by person (a child
sees only their own) and by the grant's date window. ``_access_person_field``
/ ``_access_date_field`` tell ``AccessContext.require`` how to check a single
object (used for attachments and edits).

Reminder texts are Polish and *generic* ("Pora na lek") — health details
never go into e-mail or lock-screen notifications.
"""

from __future__ import annotations

from datetime import timedelta

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
    # The medicine from the cabinet (Apteczka); ``name`` mirrors it for display.
    cabinet_item = models.ForeignKey(
        "health.CabinetItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treatments",
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


class Appointment(_PersonRecord):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    starts_at = models.DateTimeField(db_index=True)
    doctor = models.CharField(max_length=120, blank=True)
    specialty = models.CharField(max_length=120, blank=True)
    place = models.CharField(max_length=200, blank=True)
    room = models.CharField(max_length=60, blank=True, help_text="Room / office number.")
    purpose = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    cost = money_amount_field(null=True, blank=True)
    currency = currency_field()
    # The illness/event this visit is about (optional).
    condition = models.ForeignKey(
        Condition, null=True, blank=True, on_delete=models.SET_NULL, related_name="appointments"
    )

    _access_date_field = "starts_at"

    class Meta:
        ordering = ("-starts_at",)


class Symptom(_PersonRecord):
    """One observation during an illness/event — "gorączka 38,5 °C at 21:00" —
    so the course of the illness can be followed over time."""

    condition = models.ForeignKey(Condition, on_delete=models.CASCADE, related_name="symptom_log")
    observed_at = models.DateTimeField(db_index=True)
    symptom = models.CharField(max_length=80)
    value = models.CharField(max_length=40, blank=True, help_text="e.g. '38,5 °C'")

    _access_date_field = "observed_at"

    class Meta:
        ordering = ("-observed_at", "-created_at")

    def __str__(self) -> str:
        return self.symptom


class Measurement(_PersonRecord):
    """Body weight / height on a date — weight drives the dose calculator."""

    date = models.DateField(db_index=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    _access_date_field = "date"

    class Meta:
        ordering = ("-date", "-created_at")


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


# ---- Medicine cabinet (household, not per person) -------------------------


def _decimal(**kwargs) -> models.DecimalField:
    """Optional dosing quantity (mg, ml, mg/kg …)."""
    return models.DecimalField(max_digits=9, decimal_places=3, null=True, blank=True, **kwargs)


class CabinetItem(UUIDModel, TimeStamped):
    """A medicine kept at home and what it's for — the household's "what can
    I take for this?" reference (also read by the AI assistant)."""

    class Form(models.TextChoices):
        TABLETS = "tablets", "Tablets / capsules"
        SYRUP = "syrup", "Syrup / suspension"
        DROPS = "drops", "Drops"
        SPRAY = "spray", "Spray"
        OINTMENT = "ointment", "Ointment / gel"
        SACHET = "sachet", "Sachets / powder"
        SUPPOSITORY = "suppository", "Suppositories"
        OTHER = "other", "Other"

    class ForWhom(models.TextChoices):
        EVERYONE = "everyone", "Everyone"
        ADULTS = "adults", "Adults"
        CHILDREN = "children", "Children"

    name = models.CharField(max_length=120)
    substance = models.CharField(max_length=120, blank=True, help_text="Active substance.")
    form = models.CharField(max_length=12, choices=Form.choices, default=Form.TABLETS)
    indications = models.TextField(blank=True, help_text="What it's for.")
    for_whom = models.CharField(max_length=10, choices=ForWhom.choices, default=ForWhom.EVERYONE)
    min_age_months = models.PositiveSmallIntegerField(null=True, blank=True)
    dosage_notes = models.TextField(blank=True)
    notes = models.TextField(blank=True, help_text="Warnings, contraindications, …")

    # ---- dosing by body weight (optional; see dosing.py) ----
    # Strength: ``strength_mg`` of active substance per ``strength_volume_ml``
    # (syrup: 100 mg / 5 ml), or per unit (tablet/sachet) when volume is empty.
    strength_mg = _decimal()
    strength_volume_ml = _decimal()
    # Single dose: mg per kg, or ml per kg (when the leaflet says so).
    dose_mg_per_kg = _decimal()
    dose_ml_per_kg = _decimal()
    dose_max_mg = _decimal(help_text="Cap for one dose.")
    daily_max_mg_per_kg = _decimal()
    daily_max_mg = _decimal(help_text="Absolute daily cap.")
    min_interval_hours = models.PositiveSmallIntegerField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class MedicinePackage(UUIDModel, TimeStamped):
    """One physical box/bottle of a cabinet medicine.

    Many medicines only last a limited time once opened (eye drops ~28 days,
    syrups ~14). The box is usable until the *earlier* of the printed expiry
    and ``opened_on + days_after_opening``."""

    item = models.ForeignKey(CabinetItem, on_delete=models.CASCADE, related_name="packages")
    expiry_date = models.DateField(null=True, blank=True, help_text="Printed on the box.")
    opened_on = models.DateField(null=True, blank=True)
    days_after_opening = models.PositiveSmallIntegerField(null=True, blank=True)
    location = models.CharField(max_length=80, blank=True, help_text="Where it is kept.")
    notes = models.TextField(blank=True)
    finished_on = models.DateField(null=True, blank=True, help_text="Used up or thrown away.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ("finished_on", "expiry_date")

    @property
    def effective_expiry(self):
        """Last usable day, or None when nothing is known."""
        dates = [self.expiry_date]
        if self.opened_on and self.days_after_opening:
            dates.append(self.opened_on + timedelta(days=self.days_after_opening))
        known = [d for d in dates if d]
        return min(known) if known else None
