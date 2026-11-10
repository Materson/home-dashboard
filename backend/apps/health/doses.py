"""Dose planning: turn a medication's dose times into DoseLog rows + reminders.

Doses are planned a rolling ``HORIZON`` ahead (hourly beat job + on every
medication save) instead of all at once, so ongoing medicines (no end date)
work and edits only touch the future.

Each dose reminder carries "Wzięte" / "Pominięte" buttons. The service
worker POSTs their urls without a session, so each url holds a signed,
expiring token for exactly that dose and status.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from django.core import signing
from django.db.transaction import atomic
from django.utils import timezone

from apps.reminders import services as reminders

from .models import DoseLog, Medication

log = logging.getLogger(__name__)

HORIZON = timedelta(hours=48)
TOKEN_SALT = "health.dose-action"
TOKEN_MAX_AGE = timedelta(days=3)
CHANNELS = ("webpush", "email")


def parse_times(values: list[str]) -> list[time]:
    """["08:00", "20:30"] → sorted unique times; invalid entries are rejected."""
    out = set()
    for v in values:
        try:
            out.add(time.fromisoformat(v.strip()[:5]))
        except ValueError as exc:
            raise ValueError(f"invalid time {v!r}, use HH:MM") from exc
    return sorted(out)


def action_token(dose: DoseLog, status: str) -> str:
    return signing.dumps({"dose": str(dose.id), "status": status}, salt=TOKEN_SALT)


def read_action_token(token: str) -> tuple[str, str]:
    """→ (dose id, status). Raises ``signing.BadSignature`` (incl. expired)."""
    data = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    return data["dose"], data["status"]


def _recipients(med: Medication) -> list:
    """Whoever set the medication up, plus the patient if they have a login."""
    users = {u for u in (med.created_by, getattr(med.person, "user", None)) if u is not None}
    return [u for u in users if u.is_active]


def _clear_future(med: Medication, now: datetime) -> None:
    for dose in DoseLog.objects.filter(
        medication=med, status=DoseLog.Status.PENDING, scheduled_at__gt=now
    ):
        reminders.cancel_for_target(dose)
        dose.delete()


@atomic
def plan_doses(med: Medication, *, now: datetime | None = None, replace: bool = False) -> int:
    """Plan ``med``'s future doses within the horizon; returns how many exist
    there afterwards. ``replace`` (after an edit) first drops the pending
    future ones so changed times/dates take effect; the hourly top-up only
    adds what's missing. Past and answered doses are never touched."""
    now = now or timezone.now()
    if replace:
        _clear_future(med, now)
    times = parse_times(med.dose_times) if med.reminders_enabled else []
    if not times:
        if not replace:
            _clear_future(med, now)  # reminders were switched off meanwhile
        return 0

    recipients = _recipients(med)
    tz = timezone.get_current_timezone()
    first_day = max(med.start_date, timezone.localdate(now))
    last_day = timezone.localdate(now + HORIZON)
    if med.end_date:
        last_day = min(last_day, med.end_date)

    planned = 0
    day = first_day
    while day <= last_day:
        for t in times:
            at = timezone.make_aware(datetime.combine(day, t), tz)
            if not (now < at <= now + HORIZON):
                continue
            dose, created = DoseLog.objects.get_or_create(medication=med, scheduled_at=at)
            planned += 1
            if not created or dose.status != DoseLog.Status.PENDING or not recipients:
                continue
            reminders.schedule(
                None,
                title="Pora na lek",  # generic: details stay in the app
                body="Otwórz panel, aby zobaczyć szczegóły.",
                target=dose,
                recipients=recipients,
                channels=CHANNELS,
                due_at=at,
                sensitivity="private",
                actions=[
                    {
                        "action": status,
                        "title": title,
                        "url": f"/api/health/doses/action?token={action_token(dose, status)}",
                    }
                    for status, title in (("taken", "Wzięte"), ("skipped", "Pominięte"))
                ],
            )
        day += timedelta(days=1)
    return planned


def plan_all(*, now: datetime | None = None) -> int:
    """Hourly job: top up every active medication's doses."""
    now = now or timezone.now()
    today = timezone.localdate(now)
    total = 0
    for med in Medication.objects.filter(reminders_enabled=True).exclude(end_date__lt=today):
        try:
            total += plan_doses(med, now=now)
        except Exception:  # one bad row must not stop the others
            log.exception("planning doses for medication %s failed", med.id)
    return total


def set_status(dose: DoseLog, status: str) -> DoseLog:
    if status not in (DoseLog.Status.TAKEN, DoseLog.Status.SKIPPED, DoseLog.Status.PENDING):
        raise ValueError("unknown status")
    dose.status = status
    dose.status_at = timezone.now() if status != DoseLog.Status.PENDING else None
    dose.save(update_fields=["status", "status_at", "updated_at"])
    if status != DoseLog.Status.PENDING:
        reminders.cancel_for_target(dose)  # answered before it fired: don't nag
    return dose
