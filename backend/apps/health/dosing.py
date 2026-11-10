"""Weight-based dose calculation — pure Decimal, no Django.

Used by the cabinet's dose calculator and (later) the AI assistant, so both
give the same numbers.

Rules come from the leaflet:

* strength: ``strength_mg`` of active substance per ``strength_volume_ml``
  (syrup "100 mg / 5 ml" → 20 mg/ml), or per *unit* (tablet, sachet,
  suppository) when the volume is empty;
* single dose: ``dose_mg_per_kg`` x weight, or ``dose_ml_per_kg`` x weight;
  capped at ``dose_max_mg``;
* daily limit: ``daily_max_mg_per_kg`` x weight, capped at ``daily_max_mg``.

Safety: amounts to give are rounded **down** (0.1 ml, ¼ tablet), so rounding
never exceeds the calculated dose; every cap that kicked in is reported.
This is a helper, not medical advice — the UI says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal

ML_STEP = Decimal("0.1")
UNIT_STEP = Decimal("0.25")  # quarter tablet


@dataclass(frozen=True, slots=True)
class DoseRule:
    strength_mg: Decimal | None = None
    strength_volume_ml: Decimal | None = None  # None → strength is per unit
    dose_mg_per_kg: Decimal | None = None
    dose_ml_per_kg: Decimal | None = None
    dose_max_mg: Decimal | None = None
    daily_max_mg_per_kg: Decimal | None = None
    daily_max_mg: Decimal | None = None
    min_interval_hours: int | None = None
    min_age_months: int | None = None

    @property
    def mg_per_ml(self) -> Decimal | None:
        if self.strength_mg and self.strength_volume_ml:
            return self.strength_mg / self.strength_volume_ml
        return None

    @property
    def per_unit(self) -> bool:
        """Strength is per tablet/sachet rather than per ml."""
        return bool(self.strength_mg) and not self.strength_volume_ml

    @property
    def usable(self) -> bool:
        return bool(self.dose_mg_per_kg or self.dose_ml_per_kg)


@dataclass(slots=True)
class DoseResult:
    weight_kg: Decimal
    single_mg: Decimal | None = None
    single_ml: Decimal | None = None  # rounded down to 0.1 ml
    single_units: Decimal | None = None  # rounded down to ¼ tablet
    daily_max_mg: Decimal | None = None
    daily_max_ml: Decimal | None = None
    max_doses_per_day: int | None = None
    min_interval_hours: int | None = None
    warnings: list[str] = field(default_factory=list)


def _down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def calculate(rule: DoseRule, weight_kg: Decimal, *, age_months: int | None = None) -> DoseResult:
    """Dose for a person of ``weight_kg``. Warnings (codes, translated in the
    UI): ``no_rule``, ``bad_weight``, ``too_young``, ``capped_single``,
    ``capped_daily``, ``below_quarter_unit``."""
    result = DoseResult(weight_kg=weight_kg, min_interval_hours=rule.min_interval_hours)
    if not rule.usable:
        result.warnings.append("no_rule")
        return result
    if weight_kg <= 0:
        result.warnings.append("bad_weight")
        return result
    if age_months is not None and rule.min_age_months and age_months < rule.min_age_months:
        result.warnings.append("too_young")
    single_mg = _single_dose(rule, weight_kg, result)
    _daily_limit(rule, weight_kg, single_mg, result)
    return result


def _single_dose(rule: DoseRule, weight_kg: Decimal, result: DoseResult) -> Decimal | None:
    """Fill the single-dose fields; returns the (capped) dose in mg, if known."""
    mg_per_ml = rule.mg_per_ml
    if rule.dose_mg_per_kg:
        single_mg = weight_kg * rule.dose_mg_per_kg
    elif mg_per_ml:
        single_mg = weight_kg * rule.dose_ml_per_kg * mg_per_ml
    else:  # ml/kg rule and no strength: the answer is only a volume
        result.single_ml = _down(weight_kg * rule.dose_ml_per_kg, ML_STEP)
        return None

    if rule.dose_max_mg and single_mg > rule.dose_max_mg:
        single_mg = rule.dose_max_mg
        result.warnings.append("capped_single")
    result.single_mg = single_mg.quantize(Decimal("0.1"))
    if mg_per_ml:
        result.single_ml = _down(single_mg / mg_per_ml, ML_STEP)
    elif rule.per_unit:
        result.single_units = _down(single_mg / rule.strength_mg, UNIT_STEP)
        if result.single_units == 0:
            result.warnings.append("below_quarter_unit")
    return single_mg


def _daily_limit(
    rule: DoseRule, weight_kg: Decimal, single_mg: Decimal | None, result: DoseResult
) -> None:
    daily_mg = weight_kg * rule.daily_max_mg_per_kg if rule.daily_max_mg_per_kg else None
    if rule.daily_max_mg and (daily_mg is None or daily_mg > rule.daily_max_mg):
        if daily_mg is not None:
            result.warnings.append("capped_daily")
        daily_mg = rule.daily_max_mg
    if daily_mg is None:
        return
    result.daily_max_mg = daily_mg.quantize(Decimal("0.1"))
    if rule.mg_per_ml:
        result.daily_max_ml = _down(daily_mg / rule.mg_per_ml, ML_STEP)
    if single_mg:
        result.max_doses_per_day = int(daily_mg // single_mg)
