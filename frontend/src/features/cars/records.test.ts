import { describe, expect, it } from "vitest";
import { applyEdit, plusOneYear, RECORDS } from "./records";

type State = Record<string, string | boolean>;

/** Simulate the user typing `edits` in order into an empty fuel form. */
function typeInto(edits: [string, string][], start: State = {}) {
  let state: State = { litres: "", price_per_litre: "", discount: "", total_cost: "", ...start };
  let handTyped = new Set<string>();
  for (const [name, value] of edits) {
    ({ state, handTyped } = applyEdit(RECORDS.fuel, state, handTyped, name, value));
  }
  return state;
}

describe("fuel form: paid and discount derive each other", () => {
  it("computes paid from litres × price − discount", () => {
    const s = typeInto([
      ["litres", "40"],
      ["price_per_litre", "6.499"],
      ["discount", "12"],
    ]);
    expect(s.total_cost).toBe("247.96");
  });

  it("computes paid without a discount", () => {
    expect(typeInto([["litres", "40"], ["price_per_litre", "6.5"]]).total_cost).toBe("260.00");
  });

  it("works out the discount when the receipt amount is typed", () => {
    const s = typeInto([
      ["litres", "40"],
      ["price_per_litre", "6.499"],
      ["total_cost", "247.96"],
    ]);
    expect(s.discount).toBe("12.00");
  });

  it("works out the discount even if paid was typed before the price", () => {
    const s = typeInto([
      ["total_cost", "247.96"],
      ["litres", "40"],
      ["price_per_litre", "6.499"],
    ]);
    expect(s.discount).toBe("12.00");
    expect(s.total_cost).toBe("247.96"); // the typed amount is never overwritten
  });

  it("treats differences up to 0.10 as till rounding, not a discount", () => {
    const s = typeInto([
      ["litres", "40"],
      ["price_per_litre", "6.499"], // 259.96
      ["total_cost", "259.90"],
    ]);
    expect(s.discount).toBe("");
  });

  it("keeps both values when the user typed both", () => {
    const s = typeInto([
      ["litres", "40"],
      ["price_per_litre", "6.499"],
      ["discount", "5"],
      ["total_cost", "250"],
      ["litres", "41"],
    ]);
    expect(s.discount).toBe("5");
    expect(s.total_cost).toBe("250");
  });

  it("never computes a negative paid amount", () => {
    const s = typeInto([["litres", "1"], ["price_per_litre", "5"], ["discount", "50"]]);
    expect(s.total_cost).toBe("0.00");
  });
});

describe("inspection / insurance valid until", () => {
  const deadlines = (edits: [string, string][]) => {
    let state: State = { date: "2026-03-10", valid_until: "", kind: "inspection" };
    let handTyped = new Set<string>();
    for (const [name, value] of edits) {
      ({ state, handTyped } = applyEdit(RECORDS.deadlines, state, handTyped, name, value));
    }
    return state;
  };

  it("defaults to one year after the done-on date and follows it", () => {
    expect(deadlines([["date", "2026-03-10"]]).valid_until).toBe("2027-03-10");
    expect(deadlines([["date", "2026-05-02"]]).valid_until).toBe("2027-05-02");
  });

  it("keeps a date the user typed", () => {
    const s = deadlines([
      ["valid_until", "2026-09-10"], // e.g. a 6-month policy
      ["date", "2026-03-11"],
    ]);
    expect(s.valid_until).toBe("2026-09-10");
  });

  it("maps 29 February to 28 February", () => {
    expect(plusOneYear("2028-02-29")).toBe("2029-02-28");
    expect(plusOneYear("")).toBeNull();
  });
});
