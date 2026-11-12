/** Assistant API: status, conversations, messages (with photos), proposed
 *  changes, "what was sent", and the admin AI settings. */

export type Location = "cloud" | "local";
export type ProviderKind = "anthropic" | "openai" | "google" | "ollama" | "openai_compatible";
export type Policy = "off" | "local" | "cloud";

export type ProfileBrief = { name: string; kind: ProviderKind; model: string; location: Location };

export type Status = {
  can_use: boolean;
  configured: boolean;
  private_available: boolean;
  can_manage: boolean;
  chat_profile: ProfileBrief | null;
  local_profile: ProfileBrief | null;
};

export type Conversation = { id: string; title: string; private: boolean; updated_at: string };

export type ActionStatus = "proposed" | "done" | "cancelled" | "undone" | "failed";
export type Action = {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  status: ActionStatus;
  auto: boolean;
  error: string;
};

export type ChatFile = { id: string; url: string; mime_type: string; original_name: string };

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  error: boolean;
  created_at: string;
  files: ChatFile[];
  actions: Action[];
  has_calls: boolean;
};

export type Call = {
  created_at: string;
  profile_name: string;
  provider: ProviderKind;
  model: string;
  location: Location;
  modules: string[];
  sent: { role: string; text: string }[];
  images: number;
  input_tokens: number | null;
  output_tokens: number | null;
  ok: boolean;
  error: string;
};

export type Profile = {
  id: string;
  name: string;
  kind: ProviderKind;
  model: string;
  base_url: string;
  location: Location;
  vision: boolean;
  enabled: boolean;
  has_key: boolean;
};

export type ProfilePayload = Omit<Profile, "id" | "has_key"> & { api_key: string };

export type AISettings = {
  chat_profile_id: string | null;
  local_profile_id: string | null;
  policies: Record<string, Policy>;
  profiles: Profile[];
};

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api/assistant" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(resp.status, body.detail ?? `${method} ${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const assistantApi = {
  status: () => call<Status>("/status"),
  conversations: () => call<Conversation[]>("/conversations"),
  createConversation: (isPrivate: boolean) => call<Conversation>("/conversations", json("POST", { private: isPrivate })),
  renameConversation: (id: string, title: string) => call<Conversation>(`/conversations/${id}`, json("PUT", { title })),
  deleteConversation: (id: string) => call<{ deleted: boolean }>(`/conversations/${id}`, { method: "DELETE" }),
  messages: (id: string) => call<Message[]>(`/conversations/${id}/messages`),
  send: (id: string, text: string, page: string, files: File[]) => {
    const body = new FormData();
    body.append("text", text);
    body.append("page", page);
    for (const f of files) body.append("files", f);
    return call<{ question: Message; answer: Message }>(`/conversations/${id}/messages`, { method: "POST", body });
  },
  calls: (messageId: string) => call<Call[]>(`/messages/${messageId}/calls`),
  decide: (actionId: string, decision: "confirm" | "cancel" | "undo") =>
    call<Action>(`/actions/${actionId}/${decision}`, { method: "POST" }),

  settings: () => call<AISettings>("/settings"),
  saveSettings: (payload: Partial<Omit<AISettings, "profiles">>) => call<AISettings>("/settings", json("PUT", payload)),
  saveProfile: (payload: ProfilePayload, id?: string) =>
    id ? call<Profile>(`/profiles/${id}`, json("PUT", payload)) : call<Profile>("/profiles", json("POST", payload)),
  deleteProfile: (id: string) => call<{ deleted: boolean }>(`/profiles/${id}`, { method: "DELETE" }),
  testProfile: (id: string) => call<{ ok: boolean; detail: string }>(`/profiles/${id}/test`, { method: "POST" }),
};

export const ASSISTANT_KEY = ["assistant"];
