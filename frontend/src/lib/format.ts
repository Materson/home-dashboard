import i18n from "@/i18n";

/** Number in the UI language ("12 345,6" in Polish). Accepts API decimal strings. */
export function fmtNumber(value: number | string | null | undefined, digits = 0): string {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat(i18n.language, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

/** A quantity without trailing zeros: "2.00" → "2", "1.50" → "1,5", and small
 *  fractions kept (0.00393008 BTC) — up to the 8 places quantities are stored with. */
export function fmtQty(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 8 }).format(Number(value));
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

/** A month as a heading: "Listopad 2026" / "November 2026". */
export function fmtMonth(d: Date): string {
  const s = d.toLocaleDateString(i18n.language, { month: "long", year: "numeric" });
  return s.charAt(0).toUpperCase() + s.slice(1);
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
    hourCycle: "h23", // 24h in every language
  });
}

/** Local Date → "YYYY-MM-DDTHH:MM" (local time, no offset — the server applies its zone). */
export function isoDateTime(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${isoDate(d)}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** API datetime → "HH:MM", 24h in every language. */
export function fmtTime(value: string): string {
  return new Date(value).toLocaleTimeString(i18n.language, {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}
