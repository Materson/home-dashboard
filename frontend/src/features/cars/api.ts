/** Cars client. Records are plain JSON objects; their shape is described by
 *  the field definitions in `records.ts`. */

export type FuelType = "petrol" | "diesel" | "lpg" | "hybrid" | "electric";

export type CarInput = {
  name: string;
  make: string;
  model: string;
  year: number | null;
  plate: string;
  vin: string;
  fuel_type: FuelType;
  owner_id: string | null;
  initial_odometer_km: number;
  oil_interval_km: number;
  oil_interval_months: number;
  notes: string;
};
export type Car = CarInput & { id: string; archived: boolean };

export type Due = {
  due_km: number | null;
  km_left: number | null;
  due_date: string | null;
  km_eta: string | null;
  due_by: string | null;
};

export type CarSummary = {
  current_km: number;
  daily_km: string | null;
  last_oil_change_date: string | null;
  last_oil_change_km: number | null;
  oil: Due | null;
  oil_topped_up_litres: string;
  deadlines: { kind: "inspection" | "insurance" | "other"; valid_until: string; days_left: number }[];
  avg_consumption: string | null;
  last_consumption: string | null;
  consumption: { date: string; odometer_km: number; litres_per_100km: string; distance_km: number }[];
  period_month: string;
  fuel_cost_month: string;
  fuel_discounts_year: string;
  costs_year: string;
};

export type RecordKind =
  | "fuel"
  | "maintenance"
  | "oil-changes"
  | "oil-topups"
  | "deadlines"
  | "odometer";

export type CarRecord = { id: string } & Record<string, unknown>;

export type OdometerPoint = {
  date: string;
  odometer_km: number;
  source: RecordKind | "initial";
  record_id: string | null;
};

export type Person = { id: string; display_name: string };

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api/cars" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) throw new Error(`${method} ${path} failed: ${resp.status}`);
  return (await resp.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

export const carsApi = {
  list: (includeArchived: boolean) => call<Car[]>(`/?include_archived=${includeArchived}`),
  create: (body: CarInput) => call<Car>("/", json("POST", body)),
  update: (id: string, body: CarInput) => call<Car>(`/${id}`, json("PUT", body)),
  setArchived: (id: string, archived: boolean) =>
    call<Car>(`/${id}/${archived ? "archive" : "unarchive"}`, { method: "POST" }),
  /** `month`: "YYYY-MM-DD" of any day in the month whose costs to show. */
  summary: (id: string, month: string) => call<CarSummary>(`/${id}/summary?month=${month}`),

  odometerHistory: (carId: string) => call<OdometerPoint[]>(`/${carId}/odometer-history`),
  records: (carId: string, kind: RecordKind) => call<CarRecord[]>(`/${carId}/${kind}`),
  saveRecord: (carId: string, kind: RecordKind, body: Record<string, unknown>, id?: string) =>
    id
      ? call<CarRecord>(`/${carId}/${kind}/${id}`, json("PUT", body))
      : call<CarRecord>(`/${carId}/${kind}`, json("POST", body)),
  deleteRecord: (carId: string, kind: RecordKind, id: string) =>
    call<{ deleted: boolean }>(`/${carId}/${kind}/${id}`, { method: "DELETE" }),

  listPeople: async (): Promise<Person[]> => {
    const resp = await fetch("/api/people/", { credentials: "include" });
    return resp.ok ? ((await resp.json()) as Person[]) : [];
  },
};
