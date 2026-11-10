import { describe, expect, it } from "vitest";
import { RECORDS } from "@/features/cars/records";
import {
  applyFills,
  handTypedOnLoad,
  isValid,
  normalizeTime,
  parseTimes,
  toPayload,
  type FieldDef,
} from "./fields";

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

describe("24h time entry", () => {
  it("accepts the usual ways of typing a time", () => {
    for (const [typed, tidy] of [
      ["8", "08:00"],
      ["8:00", "08:00"],
      ["8.30", "08:30"],
      ["830", "08:30"],
      ["0830", "08:30"],
      ["14:30", "14:30"],
      ["2015", "20:15"],
      ["0", "00:00"],
    ]) {
      expect(normalizeTime(typed)).toBe(tidy);
    }
  });

  it("rejects non-times", () => {
    for (const bad of ["24:00", "8:60", "abc", "8:5", "12345", ""]) {
      expect(normalizeTime(bad)).toBeNull();
    }
  });

  it("dose times keep working with single-digit hours", () => {
    expect(parseTimes("20:00, 8")).toEqual(["08:00", "20:00"]);
  });

  it("date + time must both be filled in", () => {
    const appt: FieldDef[] = [{ name: "starts_at", type: "datetime", labelKey: "x", required: true }];
    expect(isValid(appt, { starts_at: "2026-03-10T" })).toBe(false);
    expect(isValid(appt, { starts_at: "T14:30" })).toBe(false);
    expect(isValid(appt, { starts_at: "2026-03-10T14:30" })).toBe(true);
    expect(toPayload(appt, { starts_at: "2026-03-10T14:30" })).toEqual({ starts_at: "2026-03-10T14:30" });
  });
});

describe("fill on pick", () => {
  const fills = { doctor: { "dr nowak": { specialty: "Pediatra", place: "Przychodnia B", room: "7" } } };

  it("fills only the fields that are still empty", () => {
    const state = { doctor: "dr Nowak", specialty: "", place: "Inne miejsce", room: "" };
    expect(applyFills(state, fills, "doctor", "dr Nowak")).toEqual({
      doctor: "dr Nowak",
      specialty: "Pediatra",
      place: "Inne miejsce", // typed by the user: kept
      room: "7",
    });
  });

  it("does nothing for an unknown value", () => {
    const state = { doctor: "dr Nowy", specialty: "" };
    expect(applyFills(state, fills, "doctor", "dr Nowy")).toBe(state);
  });
});


