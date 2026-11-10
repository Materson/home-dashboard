import { describe, expect, it } from "vitest";
import { RECORDS } from "@/features/cars/records";
import { handTypedOnLoad, isValid, parseTimes, toPayload, type FieldDef } from "./fields";

describe("times fields", () => {
  const fields: FieldDef[] = [{ name: "dose_times", type: "times", labelKey: "x" }];

  it("parses, sorts and de-duplicates HH:MM", () => {
    expect(parseTimes("20:00, 08:00 08:00")).toEqual(["08:00", "20:00"]);
    expect(toPayload(fields, { dose_times: "20:00, 08:00" })).toEqual({
      dose_times: ["08:00", "20:00"],
    });
    expect(toPayload(fields, { dose_times: "" })).toEqual({ dose_times: [] });
  });

  it("rejects the form while any entered time is invalid", () => {
    expect(isValid(fields, { dose_times: "08:00, 25:00" })).toBe(false);
    expect(isValid(fields, { dose_times: "08:00, 21:30" })).toBe(true);
  });
});

describe("editing a record with derived fields", () => {
  it("does not treat a matching derived date as hand-typed", () => {
    // Regression: dates were compared as numbers (NaN !== NaN), so an expiry
    // exactly one year after the done-on date was frozen when editing.
    const state = { kind: "inspection", date: "2026-03-10", valid_until: "2027-03-10" };
    expect(handTypedOnLoad(RECORDS.deadlines, state, true).has("valid_until")).toBe(false);
  });

  it("keeps a hand-typed expiry and a rounded paid amount", () => {
    expect(
      handTypedOnLoad(
        RECORDS.deadlines,
        { kind: "insurance", date: "2026-03-10", valid_until: "2026-09-10" },
        true,
      ).has("valid_until"),
    ).toBe(true);
    const fuel = { litres: "40", price_per_litre: "6.5", discount: "", total_cost: "259.90" };
    expect(handTypedOnLoad(RECORDS.fuel, fuel, true).has("total_cost")).toBe(true);
    expect(handTypedOnLoad(RECORDS.fuel, { ...fuel, total_cost: "260" }, true).has("total_cost")).toBe(
      false,
    );
  });
});
