/** Field definitions for each health record type (see components/records). */
import type { FieldDef } from "@/components/records/fields";

import type { HealthKind } from "./api";

const notes: FieldDef = { name: "notes", type: "textarea", labelKey: "health.f.notes" };
/** Who the entry is for — pre-set to the selected person, changeable. */
const person: FieldDef = { name: "person_id", type: "choice", labelKey: "health.f.person", required: true };

export const HEALTH_RECORDS: Record<HealthKind, FieldDef[]> = {
  conditions: [
    person,
    {
      name: "kind",
      type: "select",
      labelKey: "health.f.kind",
      options: ["illness", "injury", "chronic", "allergy", "vaccination", "other"],
      optionsKey: "health.conditionKind",
      column: true,
    },
    {
      name: "title",
      type: "text",
      labelKey: "health.f.condition",
      required: true,
      column: true,
      suggestKey: "eventTitle", // earlier events of the whole family
    },
    { name: "start_date", type: "date", labelKey: "health.f.from", required: true, column: true },
    { name: "end_date", type: "date", labelKey: "health.f.to", column: true },
    notes,
  ],
  medications: [
    person,
    {
      name: "name",
      type: "text",
      labelKey: "health.f.medicine",
      hintKey: "health.f.medicineHint",
      required: true,
      column: true,
    },
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
  appointments: [
    person,
    { name: "starts_at", type: "datetime", labelKey: "health.f.when", required: true, column: true },
    // Links the visit to an illness/event (it then shows in that event's window);
    // `purpose` says what the visit is for, e.g. a check-up with no illness behind it.
    { name: "condition_id", type: "choice", labelKey: "health.f.forCondition", hintKey: "health.f.forConditionHint" },
    // Text fields offer values from earlier visits (see appointment-suggestions);
    // picking a known doctor fills their usual specialty / place / room.
    { name: "doctor", type: "text", labelKey: "health.f.doctor", column: true },
    { name: "specialty", type: "text", labelKey: "health.f.specialty", column: true },
    { name: "place", type: "text", labelKey: "health.f.place", column: true },
    { name: "room", type: "text", labelKey: "health.f.room", column: true },
    { name: "purpose", type: "text", labelKey: "health.f.purpose", hintKey: "health.f.purposeHint" },
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
  // Dated observations within an illness/event, to follow its course.
  symptoms: [
    person,
    { name: "observed_at", type: "datetime", labelKey: "health.f.when", required: true, column: true },
    { name: "symptom", type: "text", labelKey: "health.f.symptom", required: true, column: true },
    {
      name: "value",
      type: "text",
      labelKey: "health.f.symptomValue",
      hintKey: "health.f.symptomValueHint",
      column: true,
    },
    { name: "condition_id", type: "choice", labelKey: "health.f.event", required: true, column: true },
    { ...notes, truncate: 40 },
  ],
  results: [
    person,
    { name: "date", type: "date", labelKey: "health.f.date", required: true, column: true },
    { name: "title", type: "text", labelKey: "health.f.resultTitle", required: true, column: true },
    { name: "lab", type: "text", labelKey: "health.f.lab", column: true },
    notes,
  ],
  measurements: [
    person,
    { name: "date", type: "date", labelKey: "health.f.date", required: true, column: true },
    { name: "weight_kg", type: "amount", labelKey: "health.f.weight", column: true },
    { name: "height_cm", type: "amount", labelKey: "health.f.height", column: true },
    notes,
  ],
};

export const HEALTH_TABS: { kind: HealthKind; labelKey: string }[] = [
  { kind: "conditions", labelKey: "health.tab.conditions" },
  { kind: "symptoms", labelKey: "health.tab.symptoms" },
  { kind: "medications", labelKey: "health.tab.treatments" },
  { kind: "appointments", labelKey: "health.tab.appointments" },
  { kind: "results", labelKey: "health.tab.results" },
  { kind: "measurements", labelKey: "health.tab.measurements" },
];

export const CABINET_ITEM_FIELDS: FieldDef[] = [
  { name: "name", type: "text", labelKey: "cabinet.f.name", required: true },
  { name: "substance", type: "text", labelKey: "cabinet.f.substance", hintKey: "cabinet.f.substanceHint" },
  {
    name: "form",
    type: "select",
    labelKey: "cabinet.f.form",
    options: ["tablets", "syrup", "drops", "spray", "ointment", "sachet", "suppository", "other"],
    optionsKey: "cabinet.form",
  },
  { name: "indications", type: "textarea", labelKey: "cabinet.f.indications", hintKey: "cabinet.f.indicationsHint" },
  {
    name: "for_whom",
    type: "select",
    labelKey: "cabinet.f.forWhom",
    options: ["everyone", "adults", "children"],
    optionsKey: "cabinet.forWhom",
  },
  { name: "min_age_months", type: "int", labelKey: "cabinet.f.minAge", hintKey: "cabinet.f.minAgeHint" },
  { name: "dosage_notes", type: "textarea", labelKey: "cabinet.f.dosage", hintKey: "cabinet.f.dosageHint" },
  { name: "notes", type: "textarea", labelKey: "cabinet.f.notes", hintKey: "cabinet.f.notesHint" },
  // ---- dosing by weight (optional, from the leaflet) → dose calculator ----
  { name: "strength_mg", type: "amount", scale: 3, labelKey: "cabinet.d.strengthMg", hintKey: "cabinet.d.strengthHint" },
  { name: "strength_volume_ml", type: "amount", scale: 3, labelKey: "cabinet.d.strengthVolume", hintKey: "cabinet.d.strengthVolumeHint" },
  { name: "dose_mg_per_kg", type: "amount", scale: 3, labelKey: "cabinet.d.doseMgPerKg", hintKey: "cabinet.d.doseHint" },
  { name: "dose_ml_per_kg", type: "amount", scale: 3, labelKey: "cabinet.d.doseMlPerKg" },
  { name: "dose_max_mg", type: "amount", scale: 3, labelKey: "cabinet.d.doseMax" },
  { name: "daily_max_mg_per_kg", type: "amount", scale: 3, labelKey: "cabinet.d.dailyMaxPerKg" },
  { name: "daily_max_mg", type: "amount", scale: 3, labelKey: "cabinet.d.dailyMax" },
  { name: "min_interval_hours", type: "int", labelKey: "cabinet.d.interval" },
];

export const PACKAGE_FIELDS: FieldDef[] = [
  { name: "expiry_date", type: "date", labelKey: "cabinet.p.expiry" },
  { name: "opened_on", type: "date", labelKey: "cabinet.p.openedOn" },
  {
    name: "days_after_opening",
    type: "int",
    labelKey: "cabinet.p.daysAfterOpening",
    hintKey: "cabinet.p.daysAfterOpeningHint",
  },
  { name: "location", type: "text", labelKey: "cabinet.p.location" },
  { name: "finished_on", type: "date", labelKey: "cabinet.p.finishedOn" },
  { name: "notes", type: "textarea", labelKey: "cabinet.f.notes" },
];
