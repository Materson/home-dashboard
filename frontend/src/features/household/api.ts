/** Household API: items with stock, batches, expiring list, shopping list. */

export type Category = "food" | "cleaning";
export type BatchStatus = "expired" | "soon" | "ok" | "unknown" | "finished";

export type Item = {
  id: string;
  name: string;
  category: Category;
  unit: string;
  min_quantity: string | null;
  notes: string;
  /** Left in open batches. */
  stock: string;
  next_expiry: string | null;
  below_min: boolean;
};

export type Batch = {
  id: string;
  item_id: string;
  quantity: string;
  expiry_date: string | null;
  added_on: string;
  finished_on: string | null;
  notes: string;
  status: BatchStatus;
};

export type ExpiringBatch = Batch & { item_name: string; unit: string };

export type ShoppingEntry = {
  id: string;
  name: string;
  quantity: string;
  item_id: string | null;
  unit: string | null;
  /** Added because the item ran below its minimum. */
  auto: boolean;
  done_at: string | null;
};

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api/household" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) throw new Error(`${method} ${path} failed: ${resp.status}`);
  return (await resp.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const householdApi = {
  items: (filters: { q?: string; category?: string }) => {
    const p = new URLSearchParams(Object.entries(filters).filter((e): e is [string, string] => !!e[1]));
    return call<Item[]>(`/items?${p}`);
  },
  saveItem: (payload: Record<string, unknown>, id?: string) =>
    id ? call<Item>(`/items/${id}`, json("PUT", payload)) : call<Item>("/items", json("POST", payload)),
  archiveItem: (id: string) => call<{ archived: boolean }>(`/items/${id}`, { method: "DELETE" }),
  consume: (id: string, amount = "1") => call<Item>(`/items/${id}/consume`, json("POST", { amount })),

  batches: (itemId: string, includeFinished: boolean) =>
    call<Batch[]>(`/items/${itemId}/batches?include_finished=${includeFinished}`),
  saveBatch: (payload: Record<string, unknown>, ids: { itemId?: string; batchId?: string }) =>
    ids.batchId
      ? call<Batch>(`/batches/${ids.batchId}`, json("PUT", payload))
      : call<Batch>(`/items/${ids.itemId}/batches`, json("POST", payload)),
  finishBatch: (id: string) => call<Batch>(`/batches/${id}/finish`, { method: "POST" }),
  deleteBatch: (id: string) => call<{ deleted: boolean }>(`/batches/${id}`, { method: "DELETE" }),

  expiring: (days = 7) => call<ExpiringBatch[]>(`/expiring?days=${days}`),

  shopping: () => call<ShoppingEntry[]>("/shopping"),
  addEntry: (payload: { name: string; quantity?: string; item_id?: string }) =>
    call<ShoppingEntry>("/shopping", json("POST", payload)),
  updateEntry: (id: string, payload: { name: string; quantity: string }) =>
    call<ShoppingEntry>(`/shopping/${id}`, json("PUT", payload)),
  tick: (id: string, payload: { bought?: string; expiry_date?: string | null } = {}) =>
    call<ShoppingEntry>(`/shopping/${id}/tick`, json("POST", payload)),
  untick: (id: string) => call<ShoppingEntry>(`/shopping/${id}/untick`, { method: "POST" }),
  deleteEntry: (id: string) => call<{ deleted: boolean }>(`/shopping/${id}`, { method: "DELETE" }),
  clearDone: () => call<{ deleted: number }>("/shopping/clear-done", { method: "POST" }),
};

/** Everything that shows household data — refreshed after any change. */
export const HOUSEHOLD_KEY = ["household"];
