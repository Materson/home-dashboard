/**
 * First-time setup, one-time password links, accounts, roles and access
 * grants — everything that used to need the Django admin. Problems come back
 * as `ApiProblem` with the backend's code (`detail`) and, for a rejected
 * password, the rules it broke (`codes`); `problemText` translates them.
 */
import type { TFunction } from "i18next";

export class ApiProblem extends Error {
  constructor(
    public status: number,
    public detail: string,
    public codes: string[] = [],
  ) {
    super(detail);
  }
}

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    // A public POST (setup, invite) may be the first request: get the cookie.
    if (!csrf()) await fetch("/api/csrf", { credentials: "include" });
    headers.set("X-CSRFToken", csrf());
  }
  const resp = await fetch(path, { ...init, headers, credentials: "include" });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { detail?: string; codes?: string[] };
    throw new ApiProblem(resp.status, body.detail ?? String(resp.status), body.codes ?? []);
  }
  return (await resp.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export type Locale = "pl" | "en";

// -------------------- setup and links --------------------

export type LinkInfo = { email: string; name: string; purpose: "invite" | "reset" };

export const setupApi = {
  status: () => call<{ needs_setup: boolean }>("/api/setup"),
  run: (body: { email: string; password: string; name: string; locale: Locale }) =>
    call<{ ok: true }>("/api/setup", json("POST", body)),
  linkInfo: (token: string) => call<LinkInfo>(`/api/invites/${encodeURIComponent(token)}`),
  acceptLink: (token: string, password: string) =>
    call<{ ok: true }>(`/api/invites/${encodeURIComponent(token)}`, json("POST", { password })),
};

/** The address a one-time link opens (shown once, to copy and send). */
export const linkUrl = (token: string) => `${window.location.origin}/invite/${token}`;

// -------------------- accounts --------------------

export type Account = {
  id: number;
  email: string;
  name: string;
  locale: Locale;
  is_active: boolean;
  /** Superuser: may do everything, always. */
  is_main_admin: boolean;
  has_password: boolean;
  last_login: string | null;
  roles: { id: number; name: string }[];
  person: { id: string; display_name: string; color: string } | null;
  open_link: { purpose: "invite" | "reset"; expires_at: string } | null;
};

export type NewLink = { token: string; purpose: "invite" | "reset"; expires_at: string };

export type AccountInput = {
  email: string;
  name: string;
  locale: Locale;
  role_ids: number[];
  person_id: string | null;
};

export const usersApi = {
  list: () => call<Account[]>("/api/users"),
  create: (body: Omit<AccountInput, "person_id"> & { person_id?: string | null; new_person?: boolean }) =>
    call<{ user: Account; link: NewLink }>("/api/users", json("POST", body)),
  update: (id: number, body: AccountInput & { is_active: boolean }) =>
    call<Account>(`/api/users/${id}`, json("PUT", body)),
  newLink: (id: number) => call<NewLink>(`/api/users/${id}/link`, json("POST")),
};

// -------------------- roles and grants --------------------

export type Level = "view" | "edit" | "manage";
export type Subjects = "all" | "self" | "selected";

export type Grant = {
  id: string;
  user_id: number | null;
  group_id: number | null;
  module: string;
  level: Level;
  effect: "allow" | "deny";
  subjects: Subjects;
  person_ids: string[];
  data_from: string | null;
  data_to: string | null;
  valid_until: string | null;
};

export type GrantInput = Omit<Grant, "id">;

export type Role = { id: number; name: string; builtin: boolean; members: number; grants: Grant[] };

export const accessApi = {
  meta: () => call<{ modules: string[]; levels: Level[] }>("/api/access/meta"),
  roles: () => call<Role[]>("/api/access/roles"),
  createRole: (name: string) => call<Role>("/api/access/roles", json("POST", { name })),
  renameRole: (id: number, name: string) => call<Role>(`/api/access/roles/${id}`, json("PUT", { name })),
  deleteRole: (id: number) => call<{ deleted: true }>(`/api/access/roles/${id}`, json("DELETE")),
  userGrants: (userId: number) => call<Grant[]>(`/api/access/grants?user_id=${userId}`),
  saveGrant: (body: GrantInput, id?: string) =>
    id
      ? call<Grant>(`/api/access/grants/${id}`, json("PUT", body))
      : call<Grant>("/api/access/grants", json("POST", body)),
  deleteGrant: (id: string) => call<{ deleted: true }>(`/api/access/grants/${id}`, json("DELETE")),
};

// -------------------- my account --------------------

/** allauth's own endpoint; it answers 400 with `errors: [{code}]`. */
export async function changePassword(current: string, next: string): Promise<void> {
  if (!csrf()) await fetch("/api/csrf", { credentials: "include" });
  const resp = await fetch("/api/_allauth/browser/v1/account/password/change", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
    body: JSON.stringify({ current_password: current, new_password: next }),
  });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { errors?: { code?: string; param?: string }[] };
    const errors = body.errors ?? [];
    const wrongCurrent = errors.some((e) => e.param === "current_password");
    throw new ApiProblem(
      resp.status,
      wrongCurrent ? "current_password" : errors.length ? "password" : String(resp.status),
      errors.map((e) => e.code ?? "invalid"),
    );
  }
}

// -------------------- messages --------------------

const PASSWORD_RULES = ["password_too_short", "password_too_common", "password_entirely_numeric", "password_too_similar"];

/** A problem as text for the person: the backend's code, translated (a
 *  rejected password lists the rules it broke). */
export function problemText(t: TFunction, err: unknown): string {
  if (!(err instanceof ApiProblem)) return t("problem.unknown");
  if (err.detail === "password") {
    const rules = err.codes.filter((c) => PASSWORD_RULES.includes(c));
    return rules.length ? rules.map((c) => t(`problem.${c}`)).join(" ") : t("problem.password");
  }
  if (err.status === 403) return t("problem.forbidden");
  const key = `problem.${err.detail}`;
  const text = t(key);
  return text === key ? t("problem.unknown") : text;
}
