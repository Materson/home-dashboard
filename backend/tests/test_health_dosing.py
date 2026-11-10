"""Weight-based dosing. Reference cases use typical leaflet values
(ibuprofen 100 mg/5 ml syrup, paracetamol 120 mg/5 ml, 500 mg tablets)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest

from apps.access.context import AccessContext
from apps.health import selectors, services
from apps.health.dosing import DoseRule, calculate

from .factories import AccessGrantFactory, PersonFactory, UserFactory

IBUPROFEN_SYRUP = DoseRule(
    strength_mg=D("100"),
    strength_volume_ml=D("5"),  # 20 mg/ml
    dose_mg_per_kg=D("10"),
    dose_max_mg=D("400"),
    daily_max_mg_per_kg=D("30"),
    daily_max_mg=D("1200"),
    min_interval_hours=6,
    min_age_months=3,
)


def test_syrup_mg_per_kg_gives_ml():
    r = calculate(IBUPROFEN_SYRUP, D("14"), age_months=40)
    assert r.single_mg == D("140.0")
    assert r.single_ml == D("7.0")  # 140 mg / 20 mg/ml
    assert r.daily_max_mg == D("420.0")
    assert r.daily_max_ml == D("21.0")
    assert r.max_doses_per_day == 3
    assert r.min_interval_hours == 6
    assert r.warnings == []


def test_ml_rounds_down_never_up():
    paracetamol = DoseRule(strength_mg=D("120"), strength_volume_ml=D("5"), dose_mg_per_kg=D("15"))
    r = calculate(paracetamol, D("13.3"))  # 199.5 mg / 24 mg/ml = 8.3125 ml
    assert r.single_ml == D("8.3")


def test_caps_apply_and_are_reported():
    r = calculate(IBUPROFEN_SYRUP, D("60"))  # 600 mg → capped at 400; daily 1800 → 1200
    assert r.single_mg == D("400.0")
    assert r.single_ml == D("20.0")
    assert r.daily_max_mg == D("1200.0")
    assert r.max_doses_per_day == 3
    assert {"capped_single", "capped_daily"} <= set(r.warnings)


def test_too_young_is_warned_but_still_calculated():
    r = calculate(IBUPROFEN_SYRUP, D("5"), age_months=2)
    assert "too_young" in r.warnings
    assert r.single_ml == D("2.5")


def test_ml_per_kg_rule_without_strength():
    r = calculate(DoseRule(dose_ml_per_kg=D("0.5")), D("12"))
    assert r.single_ml == D("6.0")
    assert r.single_mg is None


def test_ml_per_kg_rule_with_strength_reports_mg_too():
    rule = DoseRule(strength_mg=D("100"), strength_volume_ml=D("5"), dose_ml_per_kg=D("0.5"))
    r = calculate(rule, D("12"))  # 6 ml x 20 mg/ml
    assert (r.single_ml, r.single_mg) == (D("6.0"), D("120.0"))


def test_tablets_round_down_to_quarters():
    tablets = DoseRule(strength_mg=D("500"), dose_mg_per_kg=D("15"))
    r = calculate(tablets, D("45"))  # 675 mg = 1.35 tablet → 1.25
    assert r.single_units == D("1.25")
    assert r.single_ml is None
    r = calculate(tablets, D("5"))  # 75 mg = 0.15 tablet
    assert r.single_units == 0
    assert "below_quarter_unit" in r.warnings


def test_missing_rule_or_weight():
    assert calculate(DoseRule(strength_mg=D("100")), D("10")).warnings == ["no_rule"]
    assert calculate(IBUPROFEN_SYRUP, D("0")).warnings == ["bad_weight"]


# ---- API: person's age, scoping -------------------------------------------


@pytest.mark.django_db
def test_dose_endpoint_checks_the_persons_age(client):
    user = UserFactory()
    AccessGrantFactory(user=user, module="health", level="edit")
    ctx = AccessContext.for_user(user)
    syrup = services.save_cabinet_item(
        ctx,
        {
            "name": "Ibuprofen syrop",
            "strength_mg": D("100"),
            "strength_volume_ml": D("5"),
            "dose_mg_per_kg": D("10"),
            "min_age_months": 3,
        },
    )
    baby = PersonFactory(birth_date=date(2026, 9, 1))
    r = selectors.dose_for(ctx, syrup.id, D("5"), person_id=baby.id, today=date(2026, 11, 10))
    assert "too_young" in r.warnings  # 2 months old

    client.force_login(user)
    resp = client.get(f"/api/health/cabinet/{syrup.id}/dose?weight_kg=14,5".replace(",", "."))
    assert resp.status_code == 200
    assert resp.json()["single_ml"] == "7.2"  # 145 mg / 20 mg/ml = 7.25 → 7.2


def test_age_in_months():
    assert selectors.age_in_months(date(2023, 3, 15), date(2026, 3, 14)) == 35
    assert selectors.age_in_months(date(2023, 3, 15), date(2026, 3, 15)) == 36
    assert selectors.age_in_months(None, date(2026, 1, 1)) is None
