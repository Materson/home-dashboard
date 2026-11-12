# ruff: noqa: E501 — tool descriptions are prose for the model
"""Health (local-only by default): a person's overview and history, and the
medicine cabinet with weight-based doses. Ages only — never birth dates."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.health import selectors

from . import DATE, PERSON, STR, ToolError, ToolRun, arg_date, obj, tool
from .people import age_text, find_person

HISTORY_LIMIT = 40


def _person(run: ToolRun, name: str):
    return find_person(selectors.list_people(run.ctx), name)


@tool(
    "health_overview",
    "One person's health now: age, latest weight/height and BMI, current treatments, upcoming visits, ongoing illnesses.",
    obj({"person": PERSON}, ("person",)),
    module="health",
    policy="health",
)
def health_overview(run: ToolRun, args: dict[str, Any]) -> Any:
    person = _person(run, args.get("person", ""))
    p = selectors.health_profile(run.ctx, person.id)
    return {
        "person": person.display_name,
        "age": age_text(p["age_months"]),
        "weight_kg": p["weight_kg"],
        "weight_measured": p["weight_date"],
        "height_cm": p["height_cm"],
        "bmi": p["bmi"],
        "current_treatments": [
            {"medicine": m.name, "dosage": m.dosage, "times": m.dose_times, "until": m.end_date}
            for m in p["treatments"]
        ],
        "upcoming_visits": [
            {
                "when": timezone.localtime(v.starts_at).strftime("%Y-%m-%d %H:%M"),
                "specialty": v.specialty,
                "doctor": v.doctor,
                "purpose": v.purpose,
            }
            for v in p["upcoming_visits"]
        ],
        "ongoing": [
            {"title": c.title, "kind": c.kind, "since": c.start_date} for c in p["open_conditions"]
        ],
    }


@tool(
    "health_history",
    "A person's illnesses/events (with symptoms), visits and treatments in a date range (default: last 12 months).",
    obj({"person": PERSON, "date_from": DATE, "date_to": DATE}, ("person",)),
    module="health",
    policy="health",
)
def health_history(run: ToolRun, args: dict[str, Any]) -> Any:
    person = _person(run, args.get("person", ""))
    today = timezone.localdate()
    start = arg_date(args, "date_from") or today - timedelta(days=365)
    end = arg_date(args, "date_to") or today
    ctx = run.ctx

    def recs(kind: str):
        return selectors.list_records(ctx, kind, person_id=person.id)

    events = recs("conditions").filter(start_date__lte=end, start_date__gte=start)[:HISTORY_LIMIT]
    return {
        "person": person.display_name,
        "events": [
            {
                "title": c.title,
                "kind": c.kind,
                "from": c.start_date,
                "to": c.end_date,
                "symptoms": [
                    {
                        "when": timezone.localtime(s.observed_at).strftime("%Y-%m-%d %H:%M"),
                        "symptom": s.symptom,
                        "reading": s.value,
                        "notes": s.notes,
                    }
                    for s in recs("symptoms").filter(condition=c).order_by("observed_at")
                ],
            }
            for c in events
        ],
        "visits": [
            {
                "when": timezone.localtime(v.starts_at).strftime("%Y-%m-%d %H:%M"),
                "specialty": v.specialty,
                "doctor": v.doctor,
                "purpose": v.purpose,
                "status": v.status,
            }
            for v in recs("appointments").filter(starts_at__date__range=(start, end))[
                :HISTORY_LIMIT
            ]
        ],
        "treatments": [
            {"medicine": m.name, "dosage": m.dosage, "from": m.start_date, "to": m.end_date}
            for m in recs("medications")
            .filter(start_date__lte=end)
            .exclude(end_date__lt=start)[:HISTORY_LIMIT]
        ],
    }


@tool(
    "cabinet_find",
    "Medicines at home (Apteczka): what each is for, who may take it, packages and their real expiry. With a person, also the weight-based dose for them when the medicine has a dosing rule. Use it for 'what can X take for Y'.",
    obj(
        {
            "query": {
                "type": "string",
                "description": "Name, substance or what it's for (e.g. gorączka).",
            },
            "person": PERSON,
        }
    ),
    module="health",
    policy="health",
)
def cabinet_find(run: ToolRun, args: dict[str, Any]) -> Any:
    today = timezone.localdate()
    person = _person(run, args["person"]) if args.get("person") else None
    weight = age = None
    if person:
        profile = selectors.health_profile(run.ctx, person.id)
        weight, age = profile["weight_kg"], profile["age_months"]
    items = selectors.list_cabinet(run.ctx, q=(args.get("query") or None))
    out = []
    for item in items:
        boxes = [
            {
                "expires": p.effective_expiry,
                "status": selectors.package_status(p, today),
                "opened": p.opened_on,
            }
            for p in item.shown_packages
        ]
        row: dict[str, Any] = {
            "medicine": item.name,
            "substance": item.substance,
            "form": item.form,
            "for": item.indications,
            "for_whom": item.for_whom,
            "min_age": age_text(item.min_age_months),
            "dosage_notes": item.dosage_notes,
            "packages": boxes,
            "usable": any(b["status"] not in ("expired", "finished") for b in boxes),
        }
        if person and weight and (item.dose_mg_per_kg or item.dose_ml_per_kg):
            d = selectors.dose_for(run.ctx, item.id, weight, person_id=person.id)
            row["dose_for_person"] = {
                "weight_kg": weight,
                "age": age_text(age),
                "single_ml": d.single_ml,
                "single_mg": d.single_mg,
                "single_tablets": d.single_units,
                "max_per_day_mg": d.daily_max_mg,
                "max_doses_per_day": d.max_doses_per_day,
                "min_hours_between": d.min_interval_hours,
                "warnings": d.warnings,
            }
        elif person and not weight:
            row["dose_for_person"] = "no weight recorded — ask for the weight"
        out.append(row)
    if not out:
        raise ToolError("nothing in the cabinet matches")
    return out


__all__ = ["STR"]
