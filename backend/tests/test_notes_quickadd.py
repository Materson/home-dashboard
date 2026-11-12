"""Quick-add parsing (Polish + English). "Now" is Tuesday 10.11.2026 14:00."""

from __future__ import annotations

from datetime import datetime

import pytest

from apps.notes.quickadd import parse

NOW = datetime(2026, 11, 10, 14, 0)  # a Tuesday


@pytest.mark.parametrize(
    ("text", "title", "at", "rrule"),
    [
        ("ciasto w piekarniku za 40 min", "Ciasto w piekarniku", "2026-11-10 14:40", ""),
        ("jutro 18:00 kupić mleko", "Kupić mleko", "2026-11-11 18:00", ""),
        ("kupić mleko jutro o 18", "Kupić mleko", "2026-11-11 18:00", ""),
        ("w piątek 9:30 dentysta", "Dentysta", "2026-11-13 09:30", ""),
        ("pojutrze zadzwonić do mamy", "Zadzwonić do mamy", "2026-11-12 09:00", ""),
        ("za 2 godziny wyjąć pranie", "Wyjąć pranie", "2026-11-10 16:00", ""),
        ("za godzinę wyjąć pranie", "Wyjąć pranie", "2026-11-10 15:00", ""),
        ("za pół godziny ziemniaki", "Ziemniaki", "2026-11-10 14:30", ""),
        ("15.11 odebrać paczkę", "Odebrać paczkę", "2026-11-15 09:00", ""),
        ("odebrać paczkę 15.11 o 17", "Odebrać paczkę", "2026-11-15 17:00", ""),
        ("o 20 podlać kwiaty", "Podlać kwiaty", "2026-11-10 20:00", ""),
        ("o 9 podlać kwiaty", "Podlać kwiaty", "2026-11-11 09:00", ""),  # 9:00 passed → tomorrow
        ("remember to buy milk tomorrow 18:00", "Remember to buy milk", "2026-11-11 18:00", ""),
        ("in 10 minutes check oven", "Check oven", "2026-11-10 14:10", ""),
        ("call grandma on friday at 6pm", "Call grandma", "2026-11-13 18:00", ""),
        ("co tydzień w poniedziałek 8:00 wynieść śmieci", "Wynieść śmieci", "2026-11-16 08:00",
         "FREQ=WEEKLY;BYDAY=MO"),
        ("w każdy czwartek basen", "Basen", "2026-11-12 09:00", "FREQ=WEEKLY;BYDAY=TH"),
        ("codziennie o 20 tabletka dla psa", "Tabletka dla psa", "2026-11-10 20:00", "FREQ=DAILY"),
        ("co miesiąc 10.12 czynsz", "Czynsz", "2026-12-10 09:00", "FREQ=MONTHLY"),
        ("zadzwonić do babci", "Zadzwonić do babci", None, ""),
    ],
)  # fmt: skip
def test_parse(text, title, at, rrule):
    p = parse(text, NOW)
    assert p.title == title
    assert (p.remind_at.strftime("%Y-%m-%d %H:%M") if p.remind_at else None) == at
    assert p.rrule == rrule


def test_weekday_today_means_next_week():
    p = parse("we wtorek trening", NOW)  # it's Tuesday
    assert p.remind_at == datetime(2026, 11, 17, 9, 0)


def test_past_date_without_year_is_next_year():
    assert parse("05.01 przegląd", NOW).remind_at == datetime(2027, 1, 5, 9, 0)


def test_invalid_date_is_left_in_the_text():
    p = parse("kod 31.02", NOW)
    assert p.remind_at is None and "31.02" in p.title
