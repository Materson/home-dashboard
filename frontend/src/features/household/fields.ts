/** Form fields for household items and batches (see components/records). */
import type { FieldDef } from "@/components/records/fields";

export const ITEM_FIELDS: FieldDef[] = [
  { name: "name", type: "text", labelKey: "household.f.name", required: true },
  {
    name: "category",
    type: "select",
    labelKey: "household.f.category",
    options: ["food", "cleaning"],
    optionsKey: "household.category",
  },
  { name: "unit", type: "text", labelKey: "household.f.unit", default: "szt." },
  {
    name: "min_quantity",
    type: "amount",
    labelKey: "household.f.minQuantity",
    hintKey: "household.f.minQuantityHint",
  },
  { name: "notes", type: "textarea", labelKey: "household.f.notes" },
];

export const BATCH_FIELDS: FieldDef[] = [
  { name: "quantity", type: "amount", labelKey: "household.f.quantity", required: true },
  { name: "expiry_date", type: "date", labelKey: "household.f.expiry" },
  { name: "added_on", type: "date", labelKey: "household.f.addedOn", required: true },
  { name: "notes", type: "textarea", labelKey: "household.f.notes" },
];

/** Units offered while typing (any text is allowed). */
export const UNIT_SUGGESTIONS = ["szt.", "opak.", "l", "ml", "kg", "g", "butelka", "puszka", "rolka"];
