import type { Row } from "@/components/records/fields";

export type HealthKind = "conditions" | "medications" | "purchases" | "appointments" | "results";

export type Person = { id: string; display_name: string };

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

  list: (kind: HealthKind, personId: string) =>
    call<Row[]>(`/health/${kind}?person_id=${personId}`),
  save: (kind: HealthKind, payload: Record<string, unknown>, id?: string) =>
    id
      ? call<Row>(`/health/${kind}/${id}`, json("PUT", payload))
      : call<Row>(`/health/${kind}`, json("POST", payload)),
  remove: (kind: HealthKind, id: string) =>
    call<{ deleted: boolean }>(`/health/${kind}/${id}`, { method: "DELETE" }),

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
