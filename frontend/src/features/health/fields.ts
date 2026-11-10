/** Field definitions for each health record type (see components/records). */
import type { FieldDef } from "@/components/records/fields";

import type { HealthKind } from "./api";

const notes: FieldDef = { name: "notes", type: "textarea", labelKey: "health.f.notes" };

export const HEALTH_RECORDS: Record<HealthKind, FieldDef[]> = {
  conditions: [
    {
      name: "kind",
      type: "select",
      labelKey: "health.f.kind",
      options: ["illness", "injury", "chronic", "allergy", "vaccination", "other"],
      optionsKey: "health.conditionKind",
      column: true,
    },
    { name: "title", type: "text", labelKey: "health.f.condition", required: true, column: true },
    { name: "start_date", type: "date", labelKey: "health.f.from", required: true, column: true },
    { name: "end_date", type: "date", labelKey: "health.f.to", column: true },
    { name: "doctor", type: "text", labelKey: "health.f.doctor", column: true },
    notes,
  ],
  medications: [
    { name: "name", type: "text", labelKey: "health.f.medicine", required: true, column: true },
    { name: "dosage", type: "text", labelKey: "health.f.dosage", hintKey: "health.f.dosageHint", column: true },
    { name: "start_date", type: "date", labelKey: "health.f.from", required: true, column: true },
    { name: "end_date", type: "date", labelKey: "health.f.to", hintKey: "health.f.toHint", column: true },
    {
      name: "dose_times",
      type: "times",
      labelKey: "health.f.doseTimes",
      hintKey: "health.f.doseTimesHint",
      column: true,
    },
    { name: "reminders_enabled", type: "bool", labelKey: "health.f.reminders", default: true },
    { name: "condition_id", type: "choice", labelKey: "health.f.forCondition", column: true },
    notes,
  ],
  purchases: [
    { name: "date", type: "date", labelKey: "health.f.date", required: true, column: true },
    { name: "name", type: "text", labelKey: "health.f.whatBought", required: true, column: true },
    { name: "medication_id", type: "choice", labelKey: "health.f.medicine", column: true },
    {
      name: "cost",
      type: "amount",
      labelKey: "health.f.cost",
      required: true,
      column: true,
      currencyField: "currency",
    },
    { name: "pharmacy", type: "text", labelKey: "health.f.pharmacy", column: true },
    notes,
  ],
  appointments: [
    { name: "starts_at", type: "datetime", labelKey: "health.f.when", required: true, column: true },
    { name: "specialty", type: "text", labelKey: "health.f.specialty", column: true },
    { name: "doctor", type: "text", labelKey: "health.f.doctor", column: true },
    { name: "place", type: "text", labelKey: "health.f.place", column: true },
    { name: "purpose", type: "text", labelKey: "health.f.purpose" },
    {
      name: "status",
      type: "select",
      labelKey: "health.f.status",
      options: ["planned", "done", "cancelled"],
      optionsKey: "health.appointmentStatus",
      column: true,
    },
    { name: "cost", type: "amount", labelKey: "health.f.cost", column: true, currencyField: "currency" },
    notes,
  ],
  results: [
    { name: "date", type: "date", labelKey: "health.f.date", required: true, column: true },
    { name: "title", type: "text", labelKey: "health.f.resultTitle", required: true, column: true },
    { name: "lab", type: "text", labelKey: "health.f.lab", column: true },
    notes,
  ],
};

export const HEALTH_TABS: { kind: HealthKind; labelKey: string }[] = [
  { kind: "conditions", labelKey: "health.tab.conditions" },
  { kind: "medications", labelKey: "health.tab.medications" },
  { kind: "appointments", labelKey: "health.tab.appointments" },
  { kind: "results", labelKey: "health.tab.results" },
  { kind: "purchases", labelKey: "health.tab.purchases" },
];
