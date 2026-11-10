import i18n from "@/i18n";

/** Number in the UI language ("12 345,6" in Polish). Accepts API decimal strings. */
export function fmtNumber(value: number | string | null | undefined, digits = 0): string {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat(i18n.language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

/** Money amount with currency, e.g. "1 234,50 PLN". */
export function fmtMoney(value: number | string | null | undefined, currency = "PLN"): string {
  return value === null || value === undefined || value === ""
    ? "—"
    : `${fmtNumber(value, 2)} ${currency}`;
}

/** API date "YYYY-MM-DD" → localized short date. */
export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(i18n.language);
}

/** Local Date → API "YYYY-MM-DD" (no UTC shift, unlike toISOString). */
export function isoDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** API "YYYY-MM-DD" → local Date. */
export function parseIsoDate(value: string): Date {
  const [y, m, d] = value.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** API datetime (ISO, any offset) → localized date + time. */
export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(i18n.language, {
    dateStyle: "short",
    timeStyle: "short",
  });
}

/** Local Date → "YYYY-MM-DDTHH:MM" (local time, no offset — the server applies its zone). */
export function isoDateTime(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${isoDate(d)}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
