# ruff: noqa: E501 — tool descriptions are prose for the model
"""Cars: status (km to oil change, deadlines, consumption, costs), and
proposing a fuel entry or an odometer reading. Plates and VINs are never
returned."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.cars import selectors
from apps.cars.models import Car

from . import BOOL, DATE, INT, NUM, STR, ToolError, ToolRun, arg_date, arg_decimal, money, obj, tool

CAR = {
    "type": "string",
    "description": "Car name, e.g. Octavia. May be omitted if there is one car.",
}


def find_car(run: ToolRun, name: str | None) -> Car:
    cars = list(selectors.list_cars(run.ctx))
    if not cars:
        raise ToolError("no cars recorded")
    if not name:
        if len(cars) == 1:
            return cars[0]
        raise ToolError(f"which car? one of: {', '.join(c.name for c in cars)}")
    needle = name.strip().lower()
    for c in cars:
        if needle in (c.name.lower(), f"{c.make} {c.model}".strip().lower()):
            return c
    hits = [c for c in cars if needle in c.name.lower() or needle in c.model.lower()]
    if len(hits) == 1:
        return hits[0]
    raise ToolError(f"unknown car {name!r}; one of: {', '.join(c.name for c in cars)}")


@tool(
    "cars_status",
    "Every car: odometer, km/days to the next oil change, inspection/insurance deadlines, fuel consumption (l/100 km), fuel cost this month and all costs this year.",
    obj({}),
    module="cars",
    policy="cars",
)
def cars_status(run: ToolRun, args: dict[str, Any]) -> Any:
    out = []
    for car in selectors.list_cars(run.ctx):
        s = selectors.car_summary(run.ctx, car.id)
        out.append(
            {
                "car": car.name,
                "model": " ".join(str(x) for x in (car.make, car.model, car.year or "") if x),
                "fuel": car.fuel_type,
                "odometer_km": s.current_km,
                "avg_km_per_day": str(s.daily_km) if s.daily_km is not None else None,
                "oil_change": None
                if s.oil is None
                else {
                    "due_km": s.oil.due_km,
                    "km_left": s.oil.km_left,
                    "due_date": s.oil.due_date,
                    "estimated_by": s.oil.due_by,
                },
                "oil_topped_up_since_change_l": str(s.oil_topped_up_litres),
                "deadlines": [
                    {"kind": d.kind, "valid_until": d.valid_until, "days_left": d.days_left}
                    for d in s.deadlines
                ],
                "consumption_l_100km": {
                    "average": str(s.avg_consumption) if s.avg_consumption else None,
                    "last": str(s.last_consumption) if s.last_consumption else None,
                },
                "fuel_cost_this_month": money(s.fuel_cost_month),
                "all_costs_this_year": money(s.costs_year),
            }
        )
    return out


@tool(
    "propose_fuel_entry",
    "Propose recording a fill-up (e.g. from a fuel receipt). The user confirms the card before it is saved; it also goes to Finance.",
    obj(
        {
            "car": CAR,
            "date": DATE,
            "litres": NUM,
            "total_cost": {
                "type": "number",
                "description": "Amount actually paid, after discounts.",
            },
            "price_per_litre": NUM,
            "odometer_km": INT,
            "full_tank": BOOL,
            "station": STR,
        },
        ("litres", "total_cost"),
    ),
    module="cars",
    policy="cars",
    level="edit",
)
def propose_fuel_entry(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415

    car = find_car(run, args.get("car"))
    km = args.get("odometer_km")
    current = selectors.current_odometer(car)
    if km in (None, ""):
        raise ToolError(f"odometer_km is required (last known: {current} km) — ask the user")
    km = int(km)
    if km < current:
        raise ToolError(f"odometer_km {km} is below the last known {current} km — ask the user")
    payload = {
        "car_id": str(car.id),
        "car": car.name,
        "date": (arg_date(args, "date") or timezone.localdate()).isoformat(),
        "litres": str(arg_decimal(args, "litres", required=True, positive=True)),
        "total_cost": money(arg_decimal(args, "total_cost", required=True, positive=True)),
        "price_per_litre": str(p) if (p := arg_decimal(args, "price_per_litre")) else None,
        "odometer_km": km,
        "full_tank": bool(args.get("full_tank", True)),
        "station": str(args.get("station") or "")[:80],
    }
    return actions.propose(run, "cars.fuel", payload)


@tool(
    "propose_odometer",
    "Propose recording an odometer reading (e.g. from a dashboard photo). The user confirms the card.",
    obj({"car": CAR, "date": DATE, "odometer_km": INT}, ("odometer_km",)),
    module="cars",
    policy="cars",
    level="edit",
)
def propose_odometer(run: ToolRun, args: dict[str, Any]) -> Any:
    from apps.assistant import actions  # noqa: PLC0415

    car = find_car(run, args.get("car"))
    try:
        km = int(args["odometer_km"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ToolError("odometer_km is required") from exc
    current = selectors.current_odometer(car)
    if km < current:
        raise ToolError(f"{km} km is below the last known {current} km — ask the user")
    payload = {
        "car_id": str(car.id),
        "car": car.name,
        "date": (arg_date(args, "date") or timezone.localdate()).isoformat(),
        "odometer_km": km,
    }
    return actions.propose(run, "cars.odometer", payload)
