import type { Row } from "@/components/records/fields";

export type HealthKind =
  | "conditions"
  | "medications"
  | "appointments"
  | "symptoms"
  | "results"
  | "measurements";

export type Person = { id: string; display_name: string };

export type AppointmentSuggestions = {
  doctor: string[];
  specialty: string[];
  place: string[];
  room: string[];
  purpose: string[];
  doctors: { doctor: string; specialty: string; place: string; room: string }[];
};

export type HealthProfile = {
  person_id: string;
  display_name: string;
  birth_date: string | null;
  age_months: number | null;
  weight_kg: string | null;
  weight_date: string | null;
  height_cm: string | null;
  height_date: string | null;
  bmi: string | null;
  bmi_category: "underweight" | "normal" | "overweight" | "obese" | "child" | null;
  measurements: Row[];
  treatments: Row[];
  upcoming_visits: Row[];
  open_conditions: Row[];
};

export type DoseStatus = "pending" | "taken" | "skipped";
export type Dose = {
  id: string;
  scheduled_at: string;
  status: DoseStatus;
  medication_id: string;
  medication_name: string;
  dosage: string;
  person_id: string;
  person_name: string;
};

export type AttachmentInfo = {
  id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  url: string;
};

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) throw new Error(`${method} ${path} failed: ${resp.status}`);
  return (await resp.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const healthApi = {
  people: () => call<Person[]>("/health/people"),

  /** One record type; filter by person, illness/event or cabinet medicine. */
  list: (
    kind: HealthKind,
    filters: { person_id?: string; condition_id?: string; cabinet_item_id?: string },
  ) => {
    const p = new URLSearchParams(
      Object.entries(filters).filter((e): e is [string, string] => !!e[1]),
    );
    return call<Row[]>(`/health/${kind}?${p}`);
  },
  profile: (personId: string) => call<HealthProfile>(`/health/people/${personId}/profile`),
  save: (kind: HealthKind, payload: Record<string, unknown>, id?: string) =>
    id
      ? call<Row>(`/health/${kind}/${id}`, json("PUT", payload))
      : call<Row>(`/health/${kind}`, json("POST", payload)),
  remove: (kind: HealthKind, id: string) =>
    call<{ deleted: boolean }>(`/health/${kind}/${id}`, { method: "DELETE" }),

  appointmentSuggestions: () => call<AppointmentSuggestions>("/health/appointment-suggestions"),

  doses: (day: string, personId: string) =>
    call<Dose[]>(`/health/doses?day=${day}&person_id=${personId}`),
  setDose: (id: string, status: DoseStatus) => call<Dose>(`/health/doses/${id}`, json("POST", { status })),

  files: (resultId: string) =>
    call<AttachmentInfo[]>(`/attachments?subject_type=health.testresult&subject_id=${resultId}`),
  upload: (resultId: string, file: File) => {
    const body = new FormData();
    body.append("subject_type", "health.testresult");
    body.append("subject_id", resultId);
    body.append("file", file);
    return call<AttachmentInfo>("/attachments", { method: "POST", body });
  },
  deleteFile: (id: string) => call<{ deleted: boolean }>(`/attachments/${id}`, { method: "DELETE" }),
};

// ---- Medicine cabinet ----

export type PackageStatus = "finished" | "expired" | "soon" | "ok" | "unknown";

export type MedicinePackage = {
  id: string;
  expiry_date: string | null;
  opened_on: string | null;
  days_after_opening: number | null;
  location: string;
  notes: string;
  finished_on: string | null;
  effective_expiry: string | null;
  status: PackageStatus;
};

export type CabinetItem = {
  id: string;
  name: string;
  substance: string;
  form: string;
  indications: string;
  for_whom: "everyone" | "adults" | "children";
  min_age_months: number | null;
  dosage_notes: string;
  notes: string;
  // Dosing by weight (optional); decimals as strings.
  strength_mg: string | null;
  strength_volume_ml: string | null;
  dose_mg_per_kg: string | null;
  dose_ml_per_kg: string | null;
  dose_max_mg: string | null;
  daily_max_mg_per_kg: string | null;
  daily_max_mg: string | null;
  min_interval_hours: number | null;
  packages: MedicinePackage[];
};

export type DoseWarning =
  | "no_rule"
  | "bad_weight"
  | "too_young"
  | "capped_single"
  | "capped_daily"
  | "below_quarter_unit";

export type DoseResult = {
  weight_kg: string;
  single_mg: string | null;
  single_ml: string | null;
  single_units: string | null;
  daily_max_mg: string | null;
  daily_max_ml: string | null;
  max_doses_per_day: number | null;
  min_interval_hours: number | null;
  warnings: DoseWarning[];
};

export const cabinetApi = {
  list: (q: string, forWhom: string, includeFinished: boolean) => {
    const p = new URLSearchParams({ include_finished: String(includeFinished) });
    if (q) p.set("q", q);
    if (forWhom !== "all") p.set("for_whom", forWhom);
    return call<CabinetItem[]>(`/health/cabinet?${p}`);
  },
  saveItem: (payload: Record<string, unknown>, id?: string) =>
    id
      ? call<CabinetItem>(`/health/cabinet/${id}`, json("PUT", payload))
      : call<CabinetItem>("/health/cabinet", json("POST", payload)),
  deleteItem: (id: string) => call<{ deleted: boolean }>(`/health/cabinet/${id}`, { method: "DELETE" }),
  savePackage: (payload: Record<string, unknown>, opts: { itemId?: string; id?: string }) =>
    opts.id
      ? call<MedicinePackage>(`/health/cabinet/packages/${opts.id}`, json("PUT", payload))
      : call<MedicinePackage>(`/health/cabinet/${opts.itemId}/packages`, json("POST", payload)),
  dose: (itemId: string, weightKg: string, personId: string | null) =>
    call<DoseResult>(
      `/health/cabinet/${itemId}/dose?weight_kg=${weightKg}${personId ? `&person_id=${personId}` : ""}`,
    ),
  purchases: (itemId: string) =>
    call<{ id: string; date: string; name: string; amount: string; currency: string }[]>(
      `/health/cabinet/${itemId}/purchases`,
    ),
  deletePackage: (id: string) =>
    call<{ deleted: boolean }>(`/health/cabinet/packages/${id}`, { method: "DELETE" }),
};
