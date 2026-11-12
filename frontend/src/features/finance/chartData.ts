/** Pure helpers for the finance charts page (tested in chartData.test.ts). */
import type { MonthlyTotal, Slice } from "./api";

export type PeriodMode = "month" | "year" | "last12" | "range";

/** The longest line the server draws (monthly-totals' limit). */
export const MAX_LINE_MONTHS = 36;

const pad = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export type Period = { from: string; to: string; endMonth: Date; months: number };

/** The dates a period covers, and the months the line chart shows: the
 *  12 months ending with the chosen month / year, or — for a custom range —
 *  every month the range touches (at most 36). */
export function periodRange(mode: PeriodMode, ref: Date, range?: [Date, Date]): Period {
  if (mode === "range" && range) {
    const [start, end] = range[0] <= range[1] ? range : [range[1], range[0]];
    const spanned = (end.getFullYear() - start.getFullYear()) * 12 + end.getMonth() - start.getMonth() + 1;
    return {
      from: iso(start),
      to: iso(end),
      endMonth: new Date(end.getFullYear(), end.getMonth(), 1),
      months: Math.min(spanned, MAX_LINE_MONTHS),
    };
  }
  const y = ref.getFullYear();
  const m = ref.getMonth();
  if (mode === "year") {
    return { from: `${y}-01-01`, to: `${y}-12-31`, endMonth: new Date(y, 11, 1), months: 12 };
  }
  const last = new Date(y, m + 1, 0);
  const first = mode === "month" ? new Date(y, m, 1) : new Date(y, m - 11, 1);
  return { from: iso(first), to: iso(last), endMonth: new Date(y, m, 1), months: 12 };
}

export type PieSlice = { name: string; value: number; color: string; key: string };

/** Biggest ``keep`` slices; the rest summed as one "other" slice. */
export function topSlices(slices: Slice[], keep: number, otherLabel: string, sharedLabel = ""): PieSlice[] {
  const sorted = [...slices].sort((a, b) => Number(b.total) - Number(a.total));
  const out = sorted.slice(0, keep).map((s) => ({
    key: s.key,
    name: s.key === "shared" ? sharedLabel : s.label,
    value: Number(s.total),
    color: s.color || "#868e96",
  }));
  const rest = sorted.slice(keep).reduce((n, s) => n + Number(s.total), 0);
  if (rest > 0) out.push({ key: "other", name: otherLabel, value: rest, color: "#adb5bd" });
  return out;
}

export type MonthPoint = { month: string; income: number; expense: number; balance: number };

/** Every month of the ``months`` ending with ``endMonth`` (gaps as 0), PLN only. */
export function monthlyLine(totals: MonthlyTotal[], endMonth: Date, months = 12, currency = "PLN"): MonthPoint[] {
  const points = new Map<string, MonthPoint>();
  for (let i = months - 1; i >= 0; i--) {
    const d = new Date(endMonth.getFullYear(), endMonth.getMonth() - i, 1);
    const key = `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
    points.set(key, { month: key, income: 0, expense: 0, balance: 0 });
  }
  for (const row of totals) {
    const p = points.get(row.year_month);
    if (!p || row.currency !== currency) continue;
    if (row.kind === "income") p.income += Number(row.total);
    if (row.kind === "expense") p.expense += Number(row.total);
  }
  for (const p of points.values()) p.balance = Math.round((p.income - p.expense) * 100) / 100;
  return [...points.values()];
}
