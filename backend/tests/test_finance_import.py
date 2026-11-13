"""Finance: importing a money app's export (parsing, category paths,
duplicates) and changing many transactions at once (person, category)."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal as D

import pytest
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.access.context import AccessContext
from apps.finance import importer, selectors, services
from apps.finance.models import Category, Transaction

from .factories import AccessGrantFactory, PersonFactory, UserFactory

pytestmark = pytest.mark.django_db

# The user's own export (tab-separated, as copied from a spreadsheet).
MONEY_MANAGER = (
    "Data\tCategory\tPodkategorie\tNotatka\tPLN\tIncome/Expense\tEtykietka\tOpis\tKwota\tCurrency\n"
    "09.11.2026 22:51:44\tCar\tFuel\tpaliwo\t155,38\tExpense\t\tOrlen\t155.38\tPLN\n"
    "09.11.2026 16:19:26\tParty\t\tTańce\t220\tExpense\t\tGracja\t220.0\tPLN\n"
).encode()


@pytest.fixture
def fam():
    user, viewer = UserFactory(), UserFactory()
    AccessGrantFactory(user=user, module="finance", level="edit")
    AccessGrantFactory(user=viewer, module="finance", level="view")
    return {
        "ctx": AccessContext.for_user(user),
        "viewer": AccessContext.for_user(viewer),
        "user": user,
        "kid": PersonFactory(display_name="Zosia"),
        "food": Category.objects.filter(kind="expense", parent=None).first(),
        "salary": Category.objects.get(key="income.salary"),
    }


# ---------------- reading files ----------------


def test_reads_the_money_manager_export():
    rows, skipped = importer.parse(MONEY_MANAGER, "export.tsv")
    assert not skipped
    fuel, party = rows
    assert (fuel.date, fuel.kind, fuel.amount, fuel.currency) == (
        date(2026, 11, 9),
        "expense",
        D("155.38"),
        "PLN",
    )
    assert (fuel.category, fuel.subcategory, fuel.note, fuel.description) == (
        "Car",
        "Fuel",
        "paliwo",
        "Orlen",
    )
    assert (party.category, party.subcategory, party.amount, party.note) == (
        "Party",
        "",
        D("220.00"),
        "Tańce",
    )


def test_csv_in_windows_1250_with_another_currency_transfers_and_bad_lines():
    raw = (
        "Data;Category;Notatka;PLN;Income/Expense;Kwota;Currency\n"
        "01.10.2026;Wypłata;Pensja;8 500,00;Przychód;8500;PLN\n"
        "02.10.2026;Podróże;Hotel;431,05;Expense;100;EUR\n"
        "03.10.2026;;Na oszczędności;500;Transfer-Out;500;PLN\n"
        "jutro;Jedzenie;Obiad;30;Expense;30;PLN\n"
        "05.10.2026;Jedzenie;Nic;0;Expense;0;PLN\n"
    ).encode("cp1250")
    rows, skipped = importer.parse(raw, "eksport.csv")
    pay, hotel = rows
    assert (pay.kind, pay.amount, pay.category) == ("income", D("8500.00"), "Wypłata")
    assert (hotel.amount, hotel.currency, hotel.original) == (D("431.05"), "PLN", "100.00 EUR")
    assert [(s.line, s.reason) for s in skipped] == [(4, "transfer"), (5, "date"), (6, "zero")]


def test_no_type_column_the_sign_decides():
    raw = b'Date,Amount,Name\n2026-11-01,-12.50,Kawa\n2026-11-02,"1,234.56",Pensja\n'
    kawa, pensja = importer.parse(raw, "bank.csv")[0]
    assert (kawa.kind, kawa.amount, kawa.note) == ("expense", D("12.50"), "Kawa")
    assert (pensja.kind, pensja.amount) == ("income", D("1234.56"))


def _xlsx(header: list[str], row: list[str]) -> bytes:
    """A minimal .xlsx: the header as shared strings, the row as numbers
    (the date as an Excel serial) and an inline string."""
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    strings = "".join(f"<si><t>{h}</t></si>" for h in header)
    cols = "ABCDEFGHIJ"
    head = "".join(f'<c r="{cols[i]}1" t="s"><v>{i}</v></c>' for i in range(len(header)))
    cells = "".join(
        f'<c r="{cols[i]}2" t="inlineStr"><is><t>{v}</t></is></c>'
        if not v.replace(".", "").isdigit()
        else f'<c r="{cols[i]}2"><v>{v}</v></c>'
        for i, v in enumerate(row)
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>{strings}</sst>")
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet {ns}><sheetData><row r="1">{head}</row><row r="2">{cells}</row>'
            "</sheetData></worksheet>",
        )
    return buf.getvalue()


def test_reads_xlsx_with_excel_dates():
    serial = (date(2026, 11, 9) - importer.EXCEL_EPOCH).days
    raw = _xlsx(
        ["Data", "Category", "Podkategorie", "Notatka", "PLN", "Income/Expense"],
        [f"{serial}.9516", "Car", "Fuel", "paliwo", "155.38", "Expense"],
    )
    [row], _ = importer.parse(raw, "export.xlsx")
    assert (row.date, row.amount, row.category, row.subcategory) == (
        date(2026, 11, 9),
        D("155.38"),
        "Car",
        "Fuel",
    )


def test_files_that_cant_be_read():
    for raw, code in (
        (b"  ", "empty"),
        (b"\xd0\xcf\x11\xe0rest", "xls"),
        (b"Kolumna;Inna\n1;2\n", "columns"),
        (b"PKnot a zip", "xlsx"),
    ):
        with pytest.raises(importer.ImportProblem) as err:
            importer.parse(raw, "f")
        assert err.value.code == code


def test_amounts_in_any_format():
    cases = {
        "155,38": "155.38",
        "1 234,56": "1234.56",
        "1.234,56": "1234.56",
        "1,234.56": "1234.56",
        "1,234": "1234",
        "-12,5 zł": "-12.5",
        "(40.00)": "-40.00",
    }
    for text, value in cases.items():
        assert importer.parse_amount(text) == D(value), text
    assert importer.parse_amount("abc") is None


# ---------------- preview and import ----------------


def test_import_creates_categories_and_spots_duplicates(fam, client):
    party = services.create_category(fam["ctx"], name="party", kind="expense")  # any case
    preview = selectors.import_preview(fam["ctx"], MONEY_MANAGER, "export.tsv")
    assert [
        (c["category"], c["subcategory"], c["count"], c["match_id"]) for c in preview["categories"]
    ] == [("Car", "Fuel", 1, None), ("Party", "", 1, party.id)]
    assert not any(r["duplicate"] for r in preview["rows"])

    result = services.import_transactions(fam["ctx"], preview["rows"], person_id=fam["kid"].id)
    assert result == {"created": 2, "categories": 2}  # Car and Car > Fuel
    fuel = Category.objects.get(name="Fuel")
    assert fuel.parent.name == "Car" and fuel.color == fuel.parent.color
    tx = Transaction.objects.get(category=fuel)
    # Opis is the name, Notatka the note
    assert (tx.name, tx.notes, tx.amount, tx.person_id) == (
        "Orlen",
        "paliwo",
        D("155.38"),
        fam["kid"].id,
    )
    party_tx = Transaction.objects.get(category=party)
    assert (party_tx.name, party_tx.notes) == ("Gracja", "Tańce")

    again = selectors.import_preview(fam["ctx"], MONEY_MANAGER, "export.tsv")
    assert all(r["duplicate"] for r in again["rows"])  # same day, amount and name
    assert all(c["match_id"] for c in again["categories"])

    client.force_login(fam["user"])
    upload = SimpleUploadedFile("export.tsv", MONEY_MANAGER)
    resp = client.post("/api/finance/import/preview", {"file": upload})
    assert resp.status_code == 200 and len(resp.json()["rows"]) == 2
    old = SimpleUploadedFile("export.xls", b"\xd0\xcf\x11\xe0")
    resp = client.post("/api/finance/import/preview", {"file": old})
    assert (resp.status_code, resp.json()["detail"]) == (422, "xls")


def test_import_into_chosen_categories(fam, client):
    rows = selectors.import_preview(fam["ctx"], MONEY_MANAGER, "x.tsv")["rows"]
    built_in = Category.objects.get(key="car.fuel")
    client.force_login(fam["user"])
    resp = client.post(
        "/api/finance/import",
        {
            "rows": [{**r, "date": str(r["date"]), "amount": str(r["amount"])} for r in rows],
            "categories": [
                {
                    "kind": "expense",
                    "category": "Car",
                    "subcategory": "Fuel",
                    "target_id": str(built_in.id),
                }
            ],
        },
        content_type="application/json",
    )
    assert resp.json() == {"created": 2, "categories": 1}  # only Party is new
    tx = Transaction.objects.get(category=built_in)
    assert (tx.name, tx.notes) == ("Orlen", "paliwo")
    assert not Category.objects.filter(name="Car").exists()


def test_only_who_may_edit_finance_imports(fam):
    with pytest.raises(PermissionDenied):
        selectors.import_preview(fam["viewer"], MONEY_MANAGER, "x.tsv")
    with pytest.raises(PermissionDenied):
        services.import_transactions(fam["viewer"], [])


# ---------------- many at once ----------------


def _tx(fam, name, amount, on, category):
    return services.create_transaction(
        fam["ctx"],
        {
            "date": on,
            "amount": D(amount),
            "currency": "PLN",
            "category_id": category.id,
            "name": name,
        },
    )


def test_change_person_and_category_of_what_the_filter_finds(fam, client):
    oct_ = _tx(fam, "Przedszkole Słoneczko", "800", date(2026, 10, 5), fam["food"])
    nov = _tx(fam, "Przedszkole Słoneczko", "800", date(2026, 11, 5), fam["food"])
    pay = _tx(fam, "Pensja", "9000", date(2026, 11, 10), fam["salary"])
    school = services.create_category(fam["ctx"], name="Szkoła", kind="expense")
    by_name = selectors.TransactionFilter(q="przedszkole")  # every month

    counted = services.bulk_update_transactions(
        fam["ctx"], by_name, person="person", person_id=fam["kid"].id, dry_run=True
    )
    assert counted == {"matched": 2, "changed": 2, "wrong_kind": 0}
    assert not nov.shares.exists()  # only counted

    services.bulk_update_transactions(
        fam["ctx"], by_name, person="person", person_id=fam["kid"].id, category_id=school.id
    )
    for t in (oct_, nov):
        t.refresh_from_db()
        assert (t.person_id, t.category_id) == (fam["kid"].id, school.id)
        assert [(s.person_id, s.amount) for s in t.shares.all()] == [(fam["kid"].id, D("800"))]

    # chosen rows: an income one keeps its category
    result = services.bulk_update_transactions(
        fam["ctx"],
        selectors.TransactionFilter(),
        ids=[nov.id, pay.id],
        person="household",
        category_id=fam["food"].id,
    )
    assert result == {"matched": 2, "changed": 1, "wrong_kind": 1}
    pay.refresh_from_db()
    nov.refresh_from_db()
    assert pay.category == fam["salary"]
    assert (nov.person_id, nov.category, nov.shares.count()) == (None, fam["food"], 0)

    with pytest.raises(PermissionDenied):
        services.bulk_update_transactions(fam["viewer"], by_name, person="household")
    with pytest.raises(ValueError, match="unknown person"):
        services.bulk_update_transactions(fam["ctx"], by_name, person="person")

    client.force_login(fam["user"])
    resp = client.post(
        "/api/finance/transactions/bulk",
        {
            "filters": {"q": "przedszkole", "date_from": "2026-10-01", "date_to": "2026-10-31"},
            "person": "household",
            "dry_run": True,
        },
        content_type="application/json",
    )
    assert resp.json() == {"matched": 1, "changed": 1, "wrong_kind": 0}


def test_without_an_opis_the_note_is_the_name():
    assert importer.name_and_note("Orlen", "paliwo") == ("Orlen", "paliwo")
    assert importer.name_and_note("  ", "paliwo") == ("paliwo", "")
