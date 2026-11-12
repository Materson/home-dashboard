"""Quick add: "jutro 18:00 kupić mleko" → title "Kupić mleko", remind at
tomorrow 18:00. Rule-based (Polish + English), no AI, so it's predictable.

Understands, anywhere in the text:
- relative: "za 40 min", "za 2 godziny", "za godzinę", "za pół godziny",
  "za 3 dni", "in 10 minutes", "in an hour"
- day: "dziś/dzisiaj/today", "jutro/tomorrow", "pojutrze", a weekday
  ("w piątek", "we wtorek", "on friday"), a date "15.11" / "15.11.2027"
- time: "18:00", "o 18", "o 18:30", "godz. 18", "at 6", "at 6pm"
- repeat: "codziennie/co dzień/every day", "co tydzień/weekly",
  "co miesiąc/monthly", "co poniedziałek / w każdy poniedziałek / every monday"

A day without a time means 9:00; a time without a day means the next such
time (today, or tomorrow if it has passed); a repeating weekday without a
time also means 9:00.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

DEFAULT_TIME = time(9, 0)

# Weekday stems → 0=Monday … 6=Sunday (Polish forms with/without diacritics).
_WEEKDAYS = {
    "poniedziałek": 0, "poniedzialek": 0, "monday": 0,
    "wtorek": 1, "tuesday": 1,
    "środa": 2, "środę": 2, "sroda": 2, "srode": 2, "wednesday": 2,
    "czwartek": 3, "thursday": 3,
    "piątek": 4, "piatek": 4, "friday": 4,
    "sobota": 5, "sobotę": 5, "sobote": 5, "saturday": 5,
    "niedziela": 6, "niedzielę": 6, "niedziele": 6, "sunday": 6,
}  # fmt: skip
_RRULE_DAY = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_WD = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))

_UNITS = {
    "min": 1, "minut": 1, "minuty": 1, "minutę": 1, "minute": 1, "minutes": 1, "minuta": 1,
    "h": 60, "godz": 60, "godzin": 60, "godziny": 60, "godzinę": 60, "godzine": 60,
    "hour": 60, "hours": 60,
    "dzień": 1440, "dzien": 1440, "dni": 1440, "day": 1440, "days": 1440,
    "tydzień": 10080, "tydzien": 10080, "tygodnie": 10080, "tygodni": 10080,
    "week": 10080, "weeks": 10080,
}  # fmt: skip
_UNIT = "|".join(sorted(_UNITS, key=len, reverse=True))

_B = r"(?<![\wąćęłńóśźż])"  # word start (Polish letters included)
_E = r"(?![\wąćęłńóśźż])"  # word end

_RE_REPEAT_WEEKDAY = re.compile(
    rf"{_B}(?:co|w\s+każd[yąa]|w\s+kazd[yaą]|every)\s+({_WD}){_E}\.?", re.I
)
_RE_REPEAT = re.compile(
    rf"{_B}(codziennie|co\s+dzie[nń]|każdego\s+dnia|every\s+day|daily"
    rf"|co\s+tydzie[nń]|weekly|every\s+week"
    rf"|co\s+miesi[aą]c|monthly|every\s+month){_E}",
    re.I,
)
_RE_RELATIVE = re.compile(
    rf"{_B}(?:za|in)\s+(?:(\d+)\s*|(pół|pol|half\s+an?|an?|jedn[ąa])\s+)?({_UNIT})\.?{_E}", re.I
)
_RE_DAYWORD = re.compile(rf"{_B}(dzi[sś]|dzisiaj|today|jutro|tomorrow|pojutrze){_E}", re.I)
_RE_WEEKDAY = re.compile(rf"{_B}(?:(?:w|we|on)\s+)?({_WD}){_E}", re.I)
_RE_DATE = re.compile(r"(?<![\d.:])(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?(?![\d:])")
_RE_TIME = re.compile(
    rf"{_B}(?:(?:o|at|godz\.?|na)\s+)?(\d{{1,2}}):(\d{{2}})(?!\d)"
    rf"|{_B}(?:o|at|godz\.?)\s+(\d{{1,2}})(?:\s*(am|pm))?{_E}",
    re.I,
)


@dataclass(frozen=True)
class Parsed:
    title: str
    remind_at: datetime | None
    repeat: str  # "" / daily / weekly / monthly
    rrule: str  # e.g. "FREQ=WEEKLY;BYDAY=MO" ("" when not repeating)


def _cut(text: str, m: re.Match) -> str:
    return text[: m.start()] + " " + text[m.end() :]


def _tidy_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-" + chr(0x2013))  # incl. an en dash
    # Leftover joining words at the edges ("o", "na", "at", "w").
    text = re.sub(r"^(?:o|na|at|w|we|on)\s+|\s+(?:o|na|at|w|we|on)$", "", text, flags=re.I)
    return text[:1].upper() + text[1:] if text else ""


def parse(text: str, now: datetime) -> Parsed:  # noqa: PLR0912, PLR0915 — one readable pass
    """``now`` is local, naive or aware; the result has the same tzinfo."""
    rest = text
    repeat, byday = "", None

    if m := _RE_REPEAT_WEEKDAY.search(rest):
        repeat, byday = "weekly", _WEEKDAYS[m.group(1).lower()]
        rest = _cut(rest, m)
    elif m := _RE_REPEAT.search(rest):
        word = m.group(1).lower()
        repeat = (
            "daily"
            if word.startswith(("codzien", "co dzie", "każdego", "every day", "daily"))
            else "weekly"
            if word.startswith(("co tydz", "weekly", "every week"))
            else "monthly"
        )
        rest = _cut(rest, m)

    at: datetime | None = None
    day: date | None = None
    clock: time | None = None

    if m := _RE_RELATIVE.search(rest):
        number, word, unit = m.groups()
        if number:
            amount = float(number)
        elif word and (word.lower() in ("pół", "pol") or word.lower().startswith("half")):
            amount = 0.5
        else:
            amount = 1.0
        at = now + timedelta(minutes=amount * _UNITS[unit.lower()])
        rest = _cut(rest, m)

    if at is None:
        if m := _RE_DAYWORD.search(rest):
            w = m.group(1).lower()
            offset = 0 if w in ("dziś", "dzis", "dzisiaj", "today") else 2 if w == "pojutrze" else 1
            day = now.date() + timedelta(days=offset)
            rest = _cut(rest, m)
        elif m := _RE_DATE.search(rest):
            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
            try:
                day = date(int(y) if y else now.year, mo, d)
                if not y and day < now.date():
                    day = date(now.year + 1, mo, d)  # "15.01" in December = next year
                rest = _cut(rest, m)
            except ValueError:
                day = None
        elif byday is None and (m := _RE_WEEKDAY.search(rest)):
            wd = _WEEKDAYS[m.group(1).lower()]
            ahead = (wd - now.weekday()) % 7 or 7  # "w piątek" on a Friday = next week
            day = now.date() + timedelta(days=ahead)
            rest = _cut(rest, m)

        if m := _RE_TIME.search(rest):
            hh, mm, h_only, ampm = m.groups()
            hour, minute = (int(hh), int(mm)) if hh else (int(h_only), 0)
            if ampm and ampm.lower() == "pm" and hour < 12:  # noqa: PLR2004
                hour += 12
            if ampm and ampm.lower() == "am" and hour == 12:  # noqa: PLR2004
                hour = 0
            if hour <= 23 and minute <= 59:  # noqa: PLR2004
                clock = time(hour, minute)
                rest = _cut(rest, m)

        if byday is not None and day is None:
            ahead = (byday - now.weekday()) % 7
            day = now.date() + timedelta(days=ahead)
        if day is None and clock is not None:
            day = now.date()
        if day is not None:
            at = datetime.combine(day, clock or DEFAULT_TIME, tzinfo=now.tzinfo)
            if at <= now and (clock is not None or byday is not None) and not _explicit_day(text):
                at += timedelta(days=7 if byday is not None else 1)
        elif repeat:
            at = datetime.combine(now.date(), DEFAULT_TIME, tzinfo=now.tzinfo)
            if at <= now:
                at += timedelta(days=1)

    if at is not None:
        at = at.replace(second=0, microsecond=0)
    rule = ""
    if repeat and at is not None:
        rule = f"FREQ={repeat.upper()}"
        if repeat == "weekly":
            rule += f";BYDAY={_RRULE_DAY[at.weekday()]}"
    return Parsed(title=_tidy_title(rest), remind_at=at, repeat=repeat if at else "", rrule=rule)


def _explicit_day(text: str) -> bool:
    """A named day ("dziś 8:00" when it's already 10:00) stays as said."""
    return bool(_RE_DAYWORD.search(text) or _RE_DATE.search(text))
