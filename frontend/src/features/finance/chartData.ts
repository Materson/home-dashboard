/** Pure helpers for the finance charts page (tested in chartData.test.ts). */
import type { MonthlyTotal, SeriesPoint, Slice } from "./api";

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

const GREY = "#868e96"; // a category's default colour
const PALETTE = ["#228be6", "#fa5252", "#40c057", "#fab005", "#be4bdb", "#15aabf", "#fd7e14", "#e64980", "#82c91e", "#4c6ef5", "#12b886", "#7950f2"];

/** Biggest first; a slice keeps its own colour unless it's the default grey
 *  or a bigger slice already has it (sub-categories start in their main
 *  one's colour) — those get unused palette colours, so slices stay apart. */
export function distinctColors(slices: Slice[]): Slice[] {
  const sorted = [...slices].sort((a, b) => Number(b.total) - Number(a.total));
  const taken = new Set<string>();
  const keep = sorted.map((s) => {
    const color = (s.color || GREY).toLowerCase();
    const own = color !== GREY && !taken.has(color);
    if (own) taken.add(color);
    return own;
  });
  const free = PALETTE.filter((c) => !taken.has(c));
  let next = 0;
  return sorted.map((s, i) => (keep[i] ? s : { ...s, color: free.length ? free[next++ % free.length] : GREY }));
}

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

/** "YYYY-MM" of the ``months`` months ending with ``endMonth``, oldest first. */
export function monthKeys(endMonth: Date, months: number): string[] {
  const keys: string[] = [];
  for (let i = months - 1; i >= 0; i--) {
    const d = new Date(endMonth.getFullYear(), endMonth.getMonth() - i, 1);
    keys.push(`${d.getFullYear()}-${pad(d.getMonth() + 1)}`);
  }
  return keys;
}

/** The months ``from``..``to`` (indexes into ``monthKeys``) as dates: the
 *  first day of the one, the last day of the other. */
export function monthSpan(endMonth: Date, months: number, from: number, to: number): [Date, Date] {
  const first = endMonth.getMonth() - (months - 1);
  return [
    new Date(endMonth.getFullYear(), first + from, 1),
    new Date(endMonth.getFullYear(), first + to + 1, 0),
  ];
}

/** Every month of the ``months`` ending with ``endMonth`` (gaps as 0), PLN only. */
export function monthlyLine(totals: MonthlyTotal[], endMonth: Date, months = 12, currency = "PLN"): MonthPoint[] {
  const points = new Map<string, MonthPoint>();
  for (const key of monthKeys(endMonth, months)) points.set(key, { month: key, income: 0, expense: 0, balance: 0 });
  for (const row of totals) {
    const p = points.get(row.year_month);
    if (!p || row.currency !== currency) continue;
    if (row.kind === "income") p.income += Number(row.total);
    if (row.kind === "expense") p.expense += Number(row.total);
  }
  for (const p of points.values()) p.balance = Math.round((p.income - p.expense) * 100) / 100;
  return [...points.values()];
}

export type Line = { name: string; label: string; color: string; strokeDasharray?: string };
export type CompareChart = { data: Record<string, string | number>[]; lines: Line[]; hidden: number };

/** Lines to compare: one per key — the ``keep`` biggest (the rest counted in
 *  ``hidden``) — and a key with both expenses and income drawn twice
 *  (income dashed). Every month of the window, gaps as 0. */
export function compareLines(
  points: SeriesPoint[],
  endMonth: Date,
  months: number,
  describe: (key: string) => { label: string; color: string },
  kindLabels: { expense: string; income: string },
  keep = 8,
): CompareChart {
  const months_ = monthKeys(endMonth, months);
  const inWindow = new Set(months_);
  const byKey = new Map<string, Map<"expense" | "income", Map<string, number>>>();
  const totals = new Map<string, number>();
  for (const p of points) {
    if (!inWindow.has(p.year_month) || (p.kind !== "expense" && p.kind !== "income")) continue;
    const kinds = byKey.get(p.key) ?? new Map();
    byKey.set(p.key, kinds);
    const perMonth = kinds.get(p.kind) ?? new Map<string, number>();
    kinds.set(p.kind, perMonth);
    perMonth.set(p.year_month, (perMonth.get(p.year_month) ?? 0) + Number(p.total));
    totals.set(p.key, (totals.get(p.key) ?? 0) + Number(p.total));
  }
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1]);
  const shown = ranked.slice(0, keep);
  const colors = new Map(
    distinctColors(shown.map(([key, total]) => ({ key, label: "", color: describe(key).color, total: String(total) }))).map(
      (s) => [s.key, s.color],
    ),
  );
  const data: Record<string, string | number>[] = months_.map((month) => ({ month }));
  const lines: Line[] = [];
  for (const [key] of shown) {
    const kinds = byKey.get(key)!;
    const both = kinds.size > 1;
    for (const kind of ["expense", "income"] as const) {
      const perMonth = kinds.get(kind);
      if (!perMonth) continue;
      const name = `l${lines.length}`; // chart keys can't hold the dots of category keys
      const label = describe(key).label;
      lines.push({
        name,
        label: both ? `${label} · ${kindLabels[kind]}` : label,
        color: colors.get(key) ?? GREY,
        ...(both && kind === "income" ? { strokeDasharray: "5 5" } : {}),
      });
      data.forEach((row, i) => (row[name] = Math.round((perMonth.get(months_[i]) ?? 0) * 100) / 100));
    }
  }
  return { data, lines, hidden: ranked.length - shown.length };
}
