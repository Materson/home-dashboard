/**
 * Field definitions for each car record type. `RecordSection` renders the
 * table and the add/edit form from these, so adding a field to a record is a
 * one-line change here (plus the backend schema).
 */
import type { FieldDef } from "@/components/records/fields";

import type { RecordKind } from "./api";

// Shared field machinery; re-exported for existing imports and tests.
export { applyEdit, type FieldDef } from "@/components/records/fields";

const num = (v: string | boolean | undefined) => (typeof v === "string" && v !== "" ? Number(v) : NaN);

/** A paid amount this much below litres × price counts as a discount;
 *  smaller differences are till rounding. */
export const DISCOUNT_THRESHOLD = 0.1;

/** "YYYY-MM-DD" one year later (29 Feb → 28 Feb), or null for an empty date. */
export function plusOneYear(value: string | boolean | undefined): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [y, m, d] = value.split("-").map(Number);
  const next = new Date(y + 1, m - 1, d);
  if (next.getMonth() !== m - 1) next.setDate(0); // rolled into March → last day of Feb
  const p = (n: number) => String(n).padStart(2, "0");
  return `${next.getFullYear()}-${p(next.getMonth() + 1)}-${p(next.getDate())}`;
}

/** litres × pump price, or NaN while either is missing. */
const gross = (s: Record<string, string | boolean>) => num(s.litres) * num(s.price_per_litre);

const date: FieldDef = { name: "date", type: "date", labelKey: "cars.f.date", required: true, column: true };
const notes: FieldDef = { name: "notes", type: "textarea", labelKey: "cars.f.notes" };
const odometer = (required: boolean): FieldDef => ({
  name: "odometer_km",
  type: "int",
  labelKey: "cars.f.odometer",
  required,
  column: true,
  phoneKey: "cars.phone.km",
});
const cost = (required = false): FieldDef => ({
  name: required ? "total_cost" : "cost",
  type: "amount",
  labelKey: "cars.f.cost",
  required,
  column: true,
  currencyField: "currency",
});

export const RECORDS: Record<RecordKind, FieldDef[]> = {
  fuel: [
    date,
    odometer(true),
    { name: "litres", type: "amount", labelKey: "cars.f.litres", required: true, column: true, phoneKey: "cars.phone.litres" },
    { name: "price_per_litre", type: "amount", scale: 3, labelKey: "cars.f.pumpPrice", column: true, phoneKey: "cars.phone.perLitre" },
    // Discount and paid derive each other — whichever the user typed wins:
    //  - paid typed, discount not  → discount = litres × price − paid (if > threshold)
    //  - otherwise                 → paid = litres × price − discount
    {
      name: "discount",
      type: "amount",
      labelKey: "cars.f.discount",
      hintKey: "cars.f.discountHint",
      column: true,
      phoneKey: "cars.phone.discount",
      currencyField: "currency",
      compute: {
        from: ["litres", "price_per_litre", "total_cost"],
        active: (typed) => typed.has("total_cost"),
        fn: (s) => {
          const g = gross(s);
          const paid = num(s.total_cost);
          if (Number.isNaN(g) || Number.isNaN(paid)) return null;
          const diff = g - paid;
          return diff > DISCOUNT_THRESHOLD ? diff.toFixed(2) : "";
        },
      },
    },
    {
      ...cost(true),
      labelKey: "cars.f.paid",
      phone: "value", // phones: the date, then what was paid
      hintKey: "cars.f.paidHint",
      compute: {
        from: ["litres", "price_per_litre", "discount"],
        active: (typed) => !typed.has("total_cost"),
        fn: (s) => {
          const g = gross(s);
          if (Number.isNaN(g)) return null;
          const discount = Number.isNaN(num(s.discount)) ? 0 : num(s.discount);
          return Math.max(0, g - discount).toFixed(2);
        },
      },
    },
    { name: "full_tank", type: "bool", labelKey: "cars.f.fullTank", default: true, column: true, hintKey: "cars.f.fullTankHint" },
    { name: "station", type: "text", labelKey: "cars.f.station", column: true, phoneKey: "cars.phone.plain" },
    notes,
  ],
  maintenance: [
    date,
    {
      name: "kind",
      type: "select",
      labelKey: "cars.f.kind",
      options: ["service", "part", "repair", "issue", "other"],
      optionsKey: "cars.maintenanceKind",
      column: true,
    },
    { name: "title", type: "text", labelKey: "cars.f.title", required: true, column: true },
    odometer(false),
    cost(),
    { name: "workshop", type: "text", labelKey: "cars.f.workshop" },
    notes,
  ],
  "oil-changes": [
    date,
    odometer(true),
    { name: "oil_spec", type: "text", labelKey: "cars.f.oilSpec", column: true },
    { name: "litres", type: "amount", labelKey: "cars.f.litres" },
    { name: "with_filter", type: "bool", labelKey: "cars.f.withFilter", default: true },
    { name: "next_due_km", type: "int", labelKey: "cars.f.nextDueKm", column: true, hintKey: "cars.f.nextDueHint" },
    { name: "next_due_date", type: "date", labelKey: "cars.f.nextDueDate", column: true },
    cost(),
    notes,
  ],
  "oil-topups": [
    date,
    odometer(false),
    { name: "litres", type: "amount", labelKey: "cars.f.litres", required: true, column: true },
    notes,
  ],
  deadlines: [
    {
      name: "kind",
      type: "select",
      labelKey: "cars.f.kind",
      options: ["inspection", "insurance", "other"],
      optionsKey: "cars.deadlineKind",
      column: true,
    },
    { ...date, labelKey: "cars.f.doneOn" },
    {
      name: "valid_until",
      type: "date",
      labelKey: "cars.f.validUntil",
      hintKey: "cars.f.validUntilHint",
      required: true,
      column: true,
      phoneKey: "cars.phone.validUntil",
      // Inspection and insurance usually run a year; type another date to override.
      compute: { from: ["date"], fn: (s) => plusOneYear(s.date) },
    },
    { name: "provider", type: "text", labelKey: "cars.f.provider", column: true, phoneKey: "cars.phone.plain" },
    odometer(false),
    { ...cost(), phone: "value" }, // phones: the kind, then the cost
    notes,
  ],
  odometer: [date, odometer(true), notes],
};

/** Tabs on the car page. "service" merges service, oil changes and
 *  top-ups (ServiceSection); "odometer" is the combined km history. */
export type CarTab = "fuel" | "service" | "deadlines" | "odometer";

export const RECORD_TABS: { key: CarTab; labelKey: string }[] = [
  { key: "fuel", labelKey: "cars.tab.fuel" },
  { key: "service", labelKey: "cars.tab.service" },
  { key: "deadlines", labelKey: "cars.tab.deadlines" },
  { key: "odometer", labelKey: "cars.tab.odometer" },
];
