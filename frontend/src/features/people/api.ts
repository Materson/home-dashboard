export type Person = {
  id: string;
  display_name: string;
  birth_date: string | null;
  color: string;
  has_login: boolean;
  /** May the current user edit this person (parents: everyone; a child: maybe themself). */
  can_edit: boolean;
};

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api/people" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) throw new Error(`${method} ${path} failed: ${resp.status}`);
  return (await resp.json()) as T;
}

export const peopleApi = {
  list: () => call<Person[]>("/"),
  save: (payload: Record<string, unknown>, id?: string) =>
    id
      ? call<Person>(`/${id}`, { method: "PUT", body: JSON.stringify(payload) })
      : call<Person>("/", { method: "POST", body: JSON.stringify(payload) }),
  archive: (id: string) => call<{ archived: boolean }>(`/${id}`, { method: "DELETE" }),
};
