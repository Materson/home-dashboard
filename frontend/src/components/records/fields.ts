/**
 * Field-driven records: one field definition list per record type drives
 * the table columns, the add/edit form, defaults, derived values and the API
 * payload. Used by Cars and Health; features keep their own field lists.
 */
import { isPositiveAmount } from "@/components/AmountInput";
import { fmtDate, fmtDateTime, fmtMoney, fmtNumber, isoDate } from "@/lib/format";

export type FieldType =
  | "date"
  | "datetime" // local "YYYY-MM-DDTHH:MM"
  | "int"
  | "amount" // money or litres — comma/dot decimal, see AmountInput
  | "text"
  | "textarea"
  | "bool"
  | "select" // fixed options, labels from i18n
  | "choice" // options supplied at runtime (e.g. a person's illnesses)
  | "times"; // list of "HH:MM" (dose times)

export type FieldDef = {
  name: string;
  type: FieldType;
  labelKey: string;
  required?: boolean;
  /** Shown as a table column. */
  column?: boolean;
  /** For "select": allowed values; labels come from `${optionsKey}.${value}`. */
  options?: string[];
  optionsKey?: string;
  /** Default for a new record (required dates default to today, selects to the first option). */
  default?: string | boolean;
  /** Hint under the field. */
  hintKey?: string;
  /** Currency shown next to this amount in the table. */
  currencyField?: string;
  /** Decimal places accepted when typing an "amount" (default 2). Tables always show 2. */
  scale?: number;
  /**
   * Auto-filled from other fields until the user edits it by hand.
   * `fn` returns the new value, "" to clear, or null to leave it alone;
   * `active` (optional) decides from the hand-typed fields whether this
   * field is the derived one right now.
   */
  compute?: {
    from: string[];
    fn: (state: FormState) => string | null;
    active?: (handTyped: Set<string>) => boolean;
  };
};

export type FormValue = string | boolean;
export type FormState = Record<string, FormValue>;
export type Row = { id: string } & Record<string, unknown>;
/** Runtime options for "choice" fields, keyed by field name. */
export type Choices = Record<string, { value: string; label: string }[]>;

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

/** "08:00, 20:00" → ["08:00", "20:00"] (valid HH:MM only, sorted, unique). */
export function parseTimes(value: FormValue | undefined): string[] {
  if (typeof value !== "string") return [];
  const times = value
    .split(/[,\s]+/)
    .map((v) => v.trim())
    .filter((v) => TIME_RE.test(v));
  return [...new Set(times)].sort();
}

export function isNumeric(f: FieldDef): boolean {
  return f.type === "int" || f.type === "amount";
}

/** Table cell text. */
export function display(
  f: FieldDef,
  r: Row,
  t: (k: string) => string,
  choices: Choices = {},
): string {
  const v = r[f.name];
  if (v === null || v === undefined || v === "" || (Array.isArray(v) && !v.length)) return "—";
  switch (f.type) {
    case "date":
      return fmtDate(v as string);
    case "datetime":
      return fmtDateTime(v as string);
    case "int":
      return fmtNumber(v as number);
    case "amount":
      return f.currencyField
        ? fmtMoney(v as string, r[f.currencyField] as string)
        : fmtNumber(v as string, 2); // tables always show 2 decimals; `scale` only widens input
    case "bool":
      return v ? "✓" : "—";
    case "select":
      return t(`${f.optionsKey}.${v}`);
    case "choice":
      return choices[f.name]?.find((c) => c.value === v)?.label ?? "—";
    case "times":
      return (v as string[]).join(", ");
    default:
      return String(v);
  }
}

export function initialState(fields: FieldDef[], record: Row | null): FormState {
  const state: FormState = {};
  for (const f of fields) {
    const v = record?.[f.name];
    if (record) {
      if (f.type === "bool") state[f.name] = Boolean(v);
      else if (f.type === "times") state[f.name] = Array.isArray(v) ? v.join(", ") : "";
      else if (f.type === "datetime" && typeof v === "string") state[f.name] = v.slice(0, 16);
      else state[f.name] = v === null || v === undefined ? "" : String(v);
    } else if (f.default !== undefined) {
      state[f.name] = f.default;
    } else if (f.type === "date" && f.required) {
      state[f.name] = isoDate(new Date());
    } else if (f.type === "select") {
      state[f.name] = f.options?.[0] ?? "";
    } else {
      state[f.name] = f.type === "bool" ? false : "";
    }
  }
  if (!record) {
    // New entry: pre-fill derived fields from the defaults (e.g. valid until
    // = today + 1 year), but only those derived when nothing is hand-typed.
    for (const f of fields) {
      if (!f.compute || (f.compute.active && !f.compute.active(new Set()))) continue;
      const computed = f.compute.fn(state);
      if (computed) state[f.name] = computed;
    }
  }
  return state;
}

/** Computed fields whose stored value differs from the calculation were
 *  typed by hand (e.g. receipt rounding) — keep them when editing. */
export function handTypedOnLoad(fields: FieldDef[], state: FormState, editing: boolean): Set<string> {
  if (!editing) return new Set();
  return new Set(
    fields
      .filter((f) => {
        if (!f.compute) return false;
        const computed = f.compute.fn(state);
        return computed !== null && computed !== state[f.name] && Number(computed) !== Number(state[f.name]);
      })
      .map((f) => f.name),
  );
}

/** Form state → API payload: empty optional values become null. */
export function toPayload(fields: FieldDef[], state: FormState): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const v = state[f.name];
    if (f.type === "bool") out[f.name] = Boolean(v);
    else if (f.type === "times") out[f.name] = parseTimes(v);
    else if (v === "" || v === undefined)
      out[f.name] = f.type === "text" || f.type === "textarea" ? "" : null;
    else if (f.type === "int") out[f.name] = Math.round(Number(v));
    else out[f.name] = v;
  }
  return out;
}

export function isValid(fields: FieldDef[], state: FormState): boolean {
  return fields.every((f) => {
    const v = state[f.name];
    if (f.type === "times" && typeof v === "string" && v.trim()) {
      // every entered token must be a valid time
      return v.split(/[,\s]+/).filter(Boolean).every((tok) => TIME_RE.test(tok));
    }
    if (!f.required) return true;
    if (f.type === "amount") return isPositiveAmount(String(v));
    if (f.type === "times") return parseTimes(v).length > 0;
    return v !== "" && v !== undefined;
  });
}

/**
 * Apply one user edit to a form: store the value, mark computable fields the
 * user typed into as hand-typed, and re-derive the computed fields that
 * depend on the edited one. Pure, so the derivation rules are unit-tested.
 */
export function applyEdit(
  fields: FieldDef[],
  state: FormState,
  handTyped: Set<string>,
  name: string,
  value: FormValue,
): { state: FormState; handTyped: Set<string> } {
  const def = fields.find((f) => f.name === name);
  const typed = def?.compute ? new Set(handTyped).add(name) : handTyped;
  const next = { ...state, [name]: value };
  for (const f of fields) {
    if (!f.compute || typed.has(f.name) || f.name === name) continue;
    if (!f.compute.from.includes(name)) continue;
    if (f.compute.active && !f.compute.active(typed)) continue;
    const computed = f.compute.fn(next);
    if (computed !== null) next[f.name] = computed;
  }
  return { state: next, handTyped: typed };
}
