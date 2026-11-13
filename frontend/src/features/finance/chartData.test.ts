import { describe, expect, it } from "vitest";

import { compareLines, distinctColors, monthKeys, monthlyLine, monthSpan, periodRange, topSlices } from "./chartData";
import { equalSplit, remainder, sharesValid } from "./shares";

describe("equalSplit", () => {
  it("splits evenly and keeps every cent", () => {
    expect(equalSplit("100", ["a", "b", "c"]).map((s) => s.amount)).toEqual(["33.34", "33.33", "33.33"]);
    expect(equalSplit("600", ["a", "b"]).map((s) => s.amount)).toEqual(["300.00", "300.00"]);
    expect(equalSplit("50", [])).toEqual([]);
  });

  it("validates hand-edited parts", () => {
    const parts = [
      { person_id: "a", amount: "400" },
      { person_id: "b", amount: "150" },
    ];
    expect(sharesValid("600", parts)).toBe(false);
    expect(remainder("600", parts)).toBe("50.00");
    expect(sharesValid("550", parts)).toBe(true);
    expect(sharesValid("600", [{ person_id: "a", amount: "600" }, { person_id: "b", amount: "0" }])).toBe(false);
  });
});

describe("periodRange", () => {
  const ref = new Date(2026, 1, 15); // Feb 2026
  it("covers a month, a year, and the last 12 months", () => {
    expect(periodRange("month", ref)).toMatchObject({ from: "2026-02-01", to: "2026-02-28" });
    expect(periodRange("year", ref)).toMatchObject({ from: "2026-01-01", to: "2026-12-31" });
    expect(periodRange("last12", ref)).toMatchObject({ from: "2025-03-01", to: "2026-02-28" });
  });

  it("takes a custom range in either order, with the months it touches", () => {
    const r = periodRange("range", ref, [new Date(2026, 2, 20), new Date(2025, 11, 5)]);
    expect(r).toMatchObject({ from: "2025-12-05", to: "2026-03-20", months: 4 });
    expect(r.endMonth).toEqual(new Date(2026, 2, 1));
    const long = periodRange("range", ref, [new Date(2020, 0, 1), new Date(2026, 0, 1)]);
    expect(long.months).toBe(36);
  });
});

describe("topSlices", () => {
  it("folds small categories into one", () => {
    const slices = ["a", "b", "c", "d"].map((k, i) => ({ key: k, label: k, color: "#000", total: String(40 - i * 10) }));
    const out = topSlices(slices, 2, "Pozostałe");
    expect(out.map((s) => [s.name, s.value])).toEqual([
      ["a", 40],
      ["b", 30],
      ["Pozostałe", 30],
    ]);
  });
});

describe("distinctColors", () => {
  it("keeps own colours, recolours grey and repeated ones", () => {
    const slice = (key: string, color: string, total: string) => ({ key, label: key, color, total });
    const out = distinctColors([
      slice("small", "#FF0000", "5"),
      slice("fuel", "#ff0000", "300"),
      slice("grey", "#868e96", "100"),
      slice("blue", "#228be6", "50"),
    ]);
    expect(out.map((s) => [s.key, s.color])).toEqual([
      ["fuel", "#ff0000"],
      ["grey", "#fa5252"], // first free palette colour (blue is taken)
      ["blue", "#228be6"],
      ["small", "#40c057"],
    ]);
  });
});

describe("monthlyLine", () => {
  it("fills 12 months and computes the balance", () => {
    const line = monthlyLine(
      [
        { year_month: "2026-02", kind: "income", total: "5000", currency: "PLN" },
        { year_month: "2026-02", kind: "expense", total: "3200.50", currency: "PLN" },
        { year_month: "2026-02", kind: "expense", total: "99", currency: "EUR" },
      ],
      new Date(2026, 1, 1),
    );
    expect(line).toHaveLength(12);
    expect(monthlyLine([], new Date(2026, 1, 1), 3).map((p) => p.month)).toEqual(["2025-12", "2026-01", "2026-02"]);
    expect(line[0].month).toBe("2025-03");
    expect(line[11]).toEqual({ month: "2026-02", income: 5000, expense: 3200.5, balance: 1799.5 });
  });
});

describe("repeatKind", () => {
  it("reads the frequency back from the rule", async () => {
    const { repeatKind } = await import("./recurring");
    expect(repeatKind("FREQ=MONTHLY;INTERVAL=3")).toBe("quarterly");
    expect(repeatKind("FREQ=MONTHLY;BYMONTHDAY=-1")).toBe("monthly");
    expect(repeatKind("FREQ=WEEKLY")).toBe("weekly");
    expect(repeatKind("FREQ=YEARLY")).toBe("yearly");
  });
});

describe("investment chart axis", () => {
  // Imports the whole investments page: the first import can be slow.
  it("hugs the data so small growth is visible", { timeout: 20_000 }, async () => {
    const { valueDomain } = await import("@/features/investments/InvestmentsPage");
    const [lo, hi] = valueDomain([
      { date: "2026-01-01", value: "10000", cost: "10000" },
      { date: "2026-06-01", value: "10300", cost: "10000" },
    ]);
    expect(lo).toBeGreaterThan(9900);
    expect(hi).toBeLessThan(10400);
    expect(valueDomain([])).toEqual([0, 1]);
  });
});

describe("compareLines", () => {
  const point = (key: string, year_month: string, kind: "expense" | "income", total: string) => ({ key, year_month, kind, total });
  const names: Record<string, { label: string; color: string }> = {
    fuel: { label: "Paliwo", color: "#fa5252" },
    ola: { label: "Ola", color: "#fa5252" },
    tiny: { label: "Drobne", color: "" },
  };
  const kinds = { expense: "wydatki", income: "przychody" };

  it("draws a line per key over every month, biggest first, the rest hidden", () => {
    const chart = compareLines(
      [
        point("fuel", "2026-02", "expense", "80"),
        point("fuel", "2026-03", "expense", "300.5"),
        point("ola", "2026-03", "expense", "60"),
        point("ola", "2026-03", "income", "5000"),
        point("tiny", "2026-03", "expense", "1"),
        point("fuel", "2025-01", "expense", "999"), // outside the window
      ],
      new Date(2026, 2, 1),
      3,
      (key) => names[key],
      kinds,
      2,
    );
    expect(chart.hidden).toBe(1);
    expect(chart.lines.map((l) => [l.label, l.strokeDasharray])).toEqual([
      ["Ola · wydatki", undefined],
      ["Ola · przychody", "5 5"],
      ["Paliwo", undefined],
    ]);
    // the same colour per key, and two keys never share one
    expect(chart.lines[0].color).toBe(chart.lines[1].color);
    expect(chart.lines[2].color).not.toBe(chart.lines[0].color);
    expect(chart.data).toEqual([
      { month: "2026-01", l0: 0, l1: 0, l2: 0 },
      { month: "2026-02", l0: 0, l1: 0, l2: 80 },
      { month: "2026-03", l0: 60, l1: 5000, l2: 300.5 },
    ]);
  });
});

describe("monthSpan", () => {
  it("turns dragged months into a date range, across a year end", () => {
    const end = new Date(2026, 1, 1); // Feb 2026, 6 months: Sep 2025 .. Feb 2026
    expect(monthKeys(end, 6)).toEqual(["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]);
    expect(monthSpan(end, 6, 2, 4)).toEqual([new Date(2025, 10, 1), new Date(2026, 0, 31)]);
    expect(monthSpan(end, 6, 4, 5)).toEqual([new Date(2026, 0, 1), new Date(2026, 1, 28)]);
  });
});
