"""Reading transactions from a money app's or a bank's export: CSV / TSV
(also rows pasted from a spreadsheet) and .xlsx. Columns are found by
their names, Polish or English — e.g. Money Manager's export:

    Data | Category | Podkategorie | Notatka | PLN | Income/Expense |
    Etykietka | Opis | Kwota | Currency

Opis becomes the transaction's name and Notatka its note (``name_and_note``);
other columns (Etykietka…) are ignored.

Only parsing here (no database): ``parse`` turns the file into ``Row``s and
the lines it had to skip, with the reason. Matching categories, finding
duplicates and saving live in ``selectors.import_preview`` and
``services.import_transactions``.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree as ET

MAX_BYTES = 5 * 1024 * 1024
MAX_XLSX_UNPACKED = 60 * 1024 * 1024  # a zip bomb stops here
HEADER_SEARCH_ROWS = 10

# Our field -> header names it goes by (compared lower-case, trimmed).
COLUMNS: dict[str, tuple[str, ...]] = {
    "date": ("data", "date", "okres", "period", "data transakcji", "data operacji"),
    "category": ("category", "kategoria"),
    "subcategory": ("podkategorie", "podkategoria", "subcategory", "subcategories"),
    "note": ("notatka", "note", "nazwa", "name", "tytuł", "title"),
    "pln": ("pln",),
    "type": ("income/expense", "przychód/wydatek", "typ", "type", "rodzaj"),
    "description": ("opis", "description", "memo"),
    "amount": ("kwota", "amount", "wartość"),
    "currency": ("currency", "waluta"),
}
EXPENSE = {"expense", "exp", "exp.", "wydatek", "wydatki", "koszt", "out"}
INCOME = {"income", "inc", "inc.", "przychód", "przychod", "przychody", "dochód", "wpływ", "in"}
DATE_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d.%m.%y",
)
EXCEL_EPOCH = date(1899, 12, 30)
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class ImportProblem(ValueError):
    """The file can't be read at all; ``code`` says why (for the UI)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(slots=True)
class Row:
    line: int
    date: date
    kind: str  # "expense" | "income"
    amount: Decimal  # > 0, in ``currency``
    currency: str
    category: str
    subcategory: str
    note: str
    description: str
    original: str  # "10.00 EUR" when the amount was converted to PLN by the app


@dataclass(slots=True)
class Skipped:
    line: int
    reason: str  # "date" | "amount" | "type" | "transfer" | "zero"
    text: str  # the start of the line, to recognise it


def name_and_note(description: str, note: str) -> tuple[str, str]:
    """The transaction's name (Opis) and note (Notatka); without an Opis the
    note becomes the name."""
    return (description, note) if description.strip() else (note, "")


def parse(raw: bytes, filename: str = "") -> tuple[list[Row], list[Skipped]]:
    if len(raw) > MAX_BYTES:
        raise ImportProblem("too_big")
    table = _table(raw, filename)
    header_at, columns = _header(table)
    rows: list[Row] = []
    skipped: list[Skipped] = []
    for i, cells in enumerate(table[header_at + 1 :], start=header_at + 2):
        if not any(str(c).strip() for c in cells):
            continue
        result = _row(i, cells, columns)
        (rows if isinstance(result, Row) else skipped).append(result)
    return rows, skipped


# ---------------- reading the table ----------------


def _table(raw: bytes, filename: str) -> list[list[str]]:
    if not raw.strip():
        raise ImportProblem("empty")
    if raw.startswith(b"\xd0\xcf\x11\xe0") or filename.lower().endswith(".xls"):
        raise ImportProblem("xls")  # the old binary Excel format
    if raw.startswith(b"PK"):
        return _xlsx(raw)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1250")
    first = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = max(("\t", ";", ","), key=first.count)
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xlsx(raw: bytes) -> list[list[str]]:
    """The first sheet of an .xlsx, every cell as text (numbers as written in
    the file, e.g. a date as its Excel serial "45970.94")."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_XLSX_UNPACKED:
                raise ImportProblem("too_big")
            names = z.namelist()
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{XLSX_NS}si"):
                    shared.append("".join(t.text or "" for t in si.iter(f"{XLSX_NS}t")))
            sheets = sorted(n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
            if not sheets:
                raise ImportProblem("xlsx")
            first = "xl/worksheets/sheet1.xml" if "xl/worksheets/sheet1.xml" in names else sheets[0]
            root = ET.fromstring(z.read(first))
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as exc:
        raise ImportProblem("xlsx") from exc
    table: list[list[str]] = []
    for row in root.iter(f"{XLSX_NS}row"):
        cells: dict[int, str] = {}
        for c in row.iter(f"{XLSX_NS}c"):
            kind, v = c.get("t"), c.find(f"{XLSX_NS}v")
            if kind == "inlineStr":
                value = "".join(t.text or "" for t in c.iter(f"{XLSX_NS}t"))
            elif v is None or v.text is None:
                value = ""
            elif kind == "s":
                value = shared[int(v.text)]
            else:
                value = v.text
            cells[_col(c.get("r", "A1"))] = value
        table.append([cells.get(i, "") for i in range(max(cells, default=-1) + 1)])
    return table


def _header(table: list[list[str]]) -> tuple[int, dict[str, int]]:
    """Where the header is, and our field -> column index."""
    for at, cells in enumerate(table[:HEADER_SEARCH_ROWS]):
        names = [str(c).strip().lower() for c in cells]
        columns: dict[str, int] = {}
        for field, aliases in COLUMNS.items():
            for i, name in enumerate(names):
                if name in aliases and i not in columns.values():
                    columns[field] = i
                    break
        if "date" in columns and ("pln" in columns or "amount" in columns):
            return at, columns
    raise ImportProblem("columns")


# ---------------- reading a row ----------------


def _cell(cells: list[Any], columns: dict[str, int], field: str) -> str:
    i = columns.get(field)
    return str(cells[i]).strip() if i is not None and i < len(cells) else ""


def parse_amount(text: str) -> Decimal | None:
    """ "155,38", "1 234,56", "1,234.56", "220.0", "-12,5 zł" -> Decimal."""
    s = re.sub(r"\s", "", text)  # \s also covers the (narrow) no-break space
    negative = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^\d,.]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        thousands = "." if s.rfind(",") > s.rfind(".") else ","
        s = s.replace(thousands, "").replace(",", ".")
    elif "," in s:
        # "1,234" or "1,234,567": thousands; "155,38": decimals
        parts = s.split(",")
        s = "".join(parts) if all(len(p) == 3 for p in parts[1:]) else s.replace(",", ".")  # noqa: PLR2004
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def parse_date(text: str) -> date | None:
    text = text.strip().replace("T", " ")
    if re.fullmatch(r"\d{5}(\.\d+)?", text):  # an Excel serial (days since 1899-12-30)
        return EXCEL_EPOCH + timedelta(days=int(float(text)))
    text = re.sub(r"(\d{2}:\d{2}:\d{2})[.,]\d+$", r"\1", text)  # no fractions of a second
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _kind(text: str, amount: Decimal) -> str | None:
    t = text.strip().lower()
    if "transfer" in t or "przelew wewn" in t:
        return "transfer"
    if t in EXPENSE:
        return "expense"
    if t in INCOME:
        return "income"
    if not t:  # no type column: the sign says
        return "expense" if amount < 0 else "income"
    return None


def _row(line: int, cells: list[Any], columns: dict[str, int]) -> Row | Skipped:
    get = lambda field: _cell(cells, columns, field)  # noqa: E731
    text = " | ".join(str(c).strip() for c in cells if str(c).strip())[:80]
    day = parse_date(get("date"))
    if day is None:
        return Skipped(line, "date", text)
    original_amount = parse_amount(get("amount")) if get("amount") else None
    original_currency = (get("currency") or "PLN").upper()
    pln = parse_amount(get("pln")) if get("pln") else None
    if pln is not None:
        amount, currency = pln, "PLN"
    elif original_amount is not None:
        amount, currency = original_amount, original_currency
    else:
        return Skipped(line, "amount", text)
    kind = _kind(get("type"), amount)
    if kind is None:
        return Skipped(line, "type", text)
    if kind == "transfer":
        return Skipped(line, "transfer", text)
    if amount == 0:
        return Skipped(line, "zero", text)
    original = ""
    if currency == "PLN" and original_currency != "PLN" and original_amount is not None:
        original = f"{abs(original_amount):.2f} {original_currency}"
    return Row(
        line=line,
        date=day,
        kind=kind,
        amount=abs(amount).quantize(Decimal("0.01")),
        currency=currency,
        category=get("category"),
        subcategory=get("subcategory"),
        note=get("note"),
        description=get("description"),
        original=original,
    )
