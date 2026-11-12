"""Aliases for private data before anything goes to a cloud model.

``Pseudonymizer.hide`` replaces, in text and in tool results:
- family members' names (from People), including Polish inflected forms
  ("Zosia", "Zosi", "Zosię", "Zosią"…) → ``[P1]``
- PESEL (checksum-verified) → ``[PESEL1]``, bank account numbers → ``[KONTO1]``
- e-mail addresses, phone numbers → ``[EMAIL1]``, ``[TEL1]``
- street addresses ("ul. Długa 5/3") and postal code + town → ``[ADRES1]``
- a date of birth written in text ("ur. 12.03.2019") → ``[DATA_UR1]``
``reveal`` turns the aliases in the model's answer (and tool arguments) back.

Aliases are stable for a conversation (stored on it), so "[P1]" is the same
person in every turn. Tools never return birth dates, PESEL, VIN or plates
in the first place — this layer is the safety net for free text (notes, a
question you type). What rules can't catch reliably: a stranger's name or a
loosely written address ("u Kowalskich na Długiej") — hence the per-module
policy and the "what was sent" view.
"""

from __future__ import annotations

import re
from typing import Any

_LOWER = "a-ząćęłńóśźż"
_UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"
_WORD_END = rf"(?![{_LOWER}{_UPPER}0-9])"
_WORD_START = rf"(?<![{_LOWER}{_UPPER}0-9])"
# Polish case endings added to a name's stem.
_ENDINGS = ("owi", "ach", "ami", "em", "om", "ie", "ów", "a", "i", "y", "ę", "ą", "u", "e", "o", "")
_VOWELS = "aeiouyąęó"
# Inflected forms that are also everyday words ("mamy" = "we have").
_STOP = {"mam", "mamy"}

_RE_ACCOUNT = re.compile(r"(?<!\d)(?:PL\s?)?\d{2}(?:[ ]?\d{4}){6}(?!\d)")
_RE_PESEL = re.compile(r"(?<!\d)\d{11}(?!\d)")
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RE_PHONE = re.compile(r"(?<![\d+])(?:\+48[\s-]?)?\d{3}[\s-]?\d{3}[\s-]?\d{3}(?!\d)")
_RE_STREET = re.compile(
    rf"{_WORD_START}(?:ul\.|ulica|al\.|aleja|os\.|osiedle|pl\.|plac)\s+"
    rf"[{_UPPER}0-9][{_LOWER}{_UPPER}0-9.\-]*(?:\s+[{_UPPER}][{_LOWER}{_UPPER}.\-]*)*"
    r"\s+\d+[a-zA-Z]?(?:\s*/\s*\d+[a-zA-Z]?)?",
    re.IGNORECASE,
)
_RE_POSTAL = re.compile(rf"(?<!\d)\d{{2}}-\d{{3}}(?!\d)(?:\s+[{_UPPER}][{_LOWER}{_UPPER}\-]+)?")
_RE_BIRTH = re.compile(
    r"(?P<lead>(?:ur\.|urodzon[a-z]*|data urodzenia:?)\s*)"
    r"(?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def valid_pesel(digits: str) -> bool:
    weights = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    total = sum(int(d) * w for d, w in zip(digits[:10], weights, strict=True))
    return (10 - total % 10) % 10 == int(digits[10])


def _name_pattern(name: str) -> re.Pattern[str] | None:
    name = name.strip()
    if len(name) < 3:  # noqa: PLR2004 — "Al" would match too much
        return None
    stem = name[:-1] if name[-1].lower() in _VOWELS and len(name) > 3 else name  # noqa: PLR2004
    endings = "|".join(_ENDINGS)
    return re.compile(rf"{_WORD_START}{re.escape(stem)}(?:{endings}){_WORD_END}", re.IGNORECASE)


class Pseudonymizer:
    def __init__(self, aliases: dict[str, str] | None = None, names: list[str] | None = None):
        self.aliases: dict[str, str] = dict(aliases or {})  # "[P1]" -> "Zosia"
        self._by_real = {real.lower(): alias for alias, real in self.aliases.items()}
        # Longest names first ("Zosia Nowak" before "Zosia").
        self._names: list[tuple[str, re.Pattern[str]]] = []
        seen: set[str] = set()
        for full in sorted({n.strip() for n in (names or []) if n.strip()}, key=len, reverse=True):
            for variant in (full, full.split()[0]):
                if variant.lower() not in seen and (pat := _name_pattern(variant)):
                    seen.add(variant.lower())
                    self._names.append((full, pat))

    # -- aliases --------------------------------------------------------

    def _alias(self, prefix: str, real: str) -> str:
        key = real.lower()
        if key in self._by_real:
            return self._by_real[key]
        n = 1 + sum(
            1
            for a in self.aliases
            if a.startswith(f"[{prefix}") and a[len(prefix) + 1 : -1].isdigit()
        )
        alias = f"[{prefix}{n}]"
        self.aliases[alias] = real
        self._by_real[key] = alias
        return alias

    # -- hide -----------------------------------------------------------

    def hide(self, text: str) -> str:
        if not text:
            return text
        text = _RE_ACCOUNT.sub(lambda m: self._alias("KONTO", m.group(0)), text)
        text = _RE_PESEL.sub(
            lambda m: self._alias("PESEL", m.group(0)) if valid_pesel(m.group(0)) else m.group(0),
            text,
        )
        text = _RE_EMAIL.sub(lambda m: self._alias("EMAIL", m.group(0)), text)
        text = _RE_BIRTH.sub(
            lambda m: m.group("lead") + self._alias("DATA_UR", m.group("date")), text
        )
        text = _RE_STREET.sub(lambda m: self._alias("ADRES", m.group(0)), text)
        text = _RE_POSTAL.sub(lambda m: self._alias("ADRES", m.group(0)), text)
        text = _RE_PHONE.sub(lambda m: self._alias("TEL", m.group(0)), text)
        for full, pattern in self._names:
            text = pattern.sub(
                lambda m, full=full: (
                    m.group(0) if m.group(0).lower() in _STOP else self._alias("P", full)
                ),
                text,
            )
        return text

    def hide_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.hide(obj)
        if isinstance(obj, dict):
            return {k: self.hide_obj(v) for k, v in obj.items()}
        if isinstance(obj, list | tuple):
            return [self.hide_obj(v) for v in obj]
        return obj

    # -- reveal ---------------------------------------------------------

    def reveal(self, text: str) -> str:
        if not text or not self.aliases:
            return text
        for alias in sorted(self.aliases, key=len, reverse=True):
            real = self.aliases[alias]
            text = text.replace(alias, real)
            bare = alias[1:-1]  # models sometimes drop the brackets: P1
            text = re.sub(rf"{_WORD_START}{re.escape(bare)}{_WORD_END}", real, text)
        return text

    def reveal_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.reveal(obj)
        if isinstance(obj, dict):
            return {k: self.reveal_obj(v) for k, v in obj.items()}
        if isinstance(obj, list | tuple):
            return [self.reveal_obj(v) for v in obj]
        return obj


class Passthrough(Pseudonymizer):
    """For a local model: nothing leaves the network, nothing is replaced."""

    def hide(self, text: str) -> str:
        return text

    def reveal(self, text: str) -> str:
        return text
