/** Notes API: own and shared notes, quick add (with time parsing), sharing. */

export type Repeat = "" | "daily" | "weekly" | "monthly";
export type ChecklistItem = { text: string; done: boolean };
export type Share = { user_id: number; name: string; can_edit: boolean };

export type Note = {
  id: string;
  title: string;
  body: string;
  checklist: ChecklistItem[];
  pinned: boolean;
  /** Aware ISO datetime. */
  remind_at: string | null;
  repeat: Repeat;
  remind_others: number[];
  owner_id: number;
  owner_name: string;
  is_owner: boolean;
  can_edit: boolean;
  shares: Share[];
  attachments: number;
  archived: boolean;
  updated_at: string;
};

export type NotePayload = {
  title: string;
  body: string;
  checklist: ChecklistItem[];
  pinned: boolean;
  /** Local "YYYY-MM-DDTHH:MM" or null. */
  remind_at: string | null;
  repeat: Repeat;
  remind_others: number[];
};

export type Parsed = { title: string; remind_at: string | null; repeat: Repeat };
export type FamilyUser = { user_id: number; name: string; color: string };
export type Scope = "all" | "mine" | "shared";
export type BulkAction = "archive" | "unarchive" | "delete";

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api/notes" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) throw new Error(`${method} ${path} failed: ${resp.status}`);
  return (await resp.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const notesApi = {
  list: (scope: Scope, q: string, archived: boolean) => {
    const p = new URLSearchParams({ scope, archived: String(archived) });
    if (q) p.set("q", q);
    return call<Note[]>(`/?${p}`);
  },
  get: (id: string) => call<Note>(`/${id}`),
  save: (payload: NotePayload, id?: string) =>
    id ? call<Note>(`/${id}`, json("PUT", payload)) : call<Note>("/", json("POST", payload)),
  remove: (id: string) => call<{ deleted: boolean }>(`/${id}`, { method: "DELETE" }),
  quick: (text: string) => call<Note>("/quick", json("POST", { text })),
  parse: (text: string) => call<Parsed>(`/parse?${new URLSearchParams({ text })}`),
  people: () => call<FamilyUser[]>("/people"),
  archive: (id: string, archived: boolean) => call<Note>(`/${id}/archive`, json("POST", { archived })),
  pin: (id: string, pinned: boolean) => call<Note>(`/${id}/pin`, json("POST", { pinned })),
  /** Your own notes only — all or nothing. */
  bulk: (ids: string[], action: BulkAction) => call<{ count: number }>("/bulk", json("POST", { ids, action })),
  toggle: (id: string, index: number, done: boolean) =>
    call<Note>(`/${id}/checklist/${index}`, json("POST", { done })),
  setShares: (id: string, shares: { user_id: number; can_edit: boolean }[]) =>
    call<Note>(`/${id}/shares`, json("PUT", shares)),
};

export const NOTES_KEY = ["notes"];
