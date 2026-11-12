/** Investments API: assets with their value, purchases (lots), manual
 *  values, bond periods, portfolio totals and series, GUS inflation. */

export type AssetKind = "gold" | "silver" | "crypto" | "stock" | "bond" | "other";
export type Share = { user_id: number; name: string; can_edit: boolean };
export type FamilyUser = { user_id: number; name: string };
export type Unit = "oz" | "g" | "pcs";

export type Lot = {
  id: string;
  bought_on: string;
  quantity: string;
  price_total: string;
  sold_on: string | null;
  sold_amount: string | null;
  rate_overrides: Record<string, string>;
  notes: string;
};

export type AssetInput = {
  name: string;
  kind: AssetKind;
  unit: Unit;
  symbol: string;
  person_id: string | null;
  bond_type: string;
  bond_first_rate: string | null;
  bond_margin: string | null;
  /** "Other" with interest: % a year, how often it's added, term in months. */
  rate: string | null;
  compounding: "none" | "monthly" | "quarterly" | "yearly";
  term_months: number | null;
  notes: string;
};

export type Asset = AssetInput & {
  id: string;
  archived: boolean;
  /** Private to its owner unless shared (view / edit). */
  owner_name: string;
  is_owner: boolean;
  can_edit: boolean;
  shares: Share[];
  lots: Lot[];
  quantity: string;
  cost: string;
  value: string;
  gain: string;
  gain_pct: string | null;
  realized: string;
  paid_out: string;
  price_date: string | null;
  /** Some value is a guess (no price yet, or a bond rate not known yet). */
  estimated: boolean;
};

export type Point = { date: string; value: string; cost: string };

export type Portfolio = {
  value: string;
  cost: string;
  gain: string;
  paid_out: string;
  realized: string;
  by_kind: Partial<Record<AssetKind, string>>;
  series: Point[];
};

export type Period = {
  number: number;
  start: string;
  end: string;
  rate: string | null;
  source: "first" | "inflation" | "fixed" | "override" | "carried" | "unknown";
  inflation: string | null;
};

export type Inflation = { year: number; month: number; index: string; manual: boolean };
export type BondType = { code: string; months: number; indexed: boolean; floating: boolean; capitalised: boolean };

export type LotInput = { bought_on: string; quantity: string; price_total: string; notes?: string };

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api/investments" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? `${method} ${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });
const months = (m: number | null) => (m ? `?months=${m}` : "");

export const investmentsApi = {
  assets: () => call<Asset[]>("/assets"),
  saveAsset: (body: AssetInput, id?: string) =>
    id ? call<Asset>(`/assets/${id}`, json("PUT", body)) : call<Asset>("/assets", json("POST", body)),
  setShares: (id: string, shares: { user_id: number; can_edit: boolean }[]) =>
    call<Asset>(`/assets/${id}/shares`, json("PUT", shares)),
  people: () => call<FamilyUser[]>("/people"),
  archiveAsset: (id: string) => call<{ archived: boolean }>(`/assets/${id}`, { method: "DELETE" }),
  addLot: (assetId: string, body: LotInput) => call<Lot>(`/assets/${assetId}/lots`, json("POST", body)),
  updateLot: (id: string, body: LotInput) => call<Lot>(`/lots/${id}`, json("PUT", body)),
  deleteLot: (id: string) => call<{ deleted: boolean }>(`/lots/${id}`, { method: "DELETE" }),
  sellLot: (id: string, body: { sold_on: string; sold_amount: string }) =>
    call<Lot>(`/lots/${id}/sell`, json("POST", body)),
  periods: (lotId: string) => call<Period[]>(`/lots/${lotId}/periods`),
  overrideRate: (lotId: string, period: number, rate: string | null) =>
    call<Lot>(`/lots/${lotId}/periods/${period}`, json("PUT", { rate })),
  setValue: (assetId: string, body: { on: string; unit_price?: string; total?: string }) =>
    call<{ date: string; unit_price: string }>(`/assets/${assetId}/values`, json("POST", body)),
  series: (assetId: string, m: number | null) => call<Point[]>(`/assets/${assetId}/series${months(m)}`),
  portfolio: (f: { months?: number | null; kind?: AssetKind | null; from?: string; to?: string; openOnly?: boolean }) => {
    const p = new URLSearchParams();
    if (f.openOnly) p.set("open_only", "true");
    if (f.months) p.set("months", String(f.months));
    if (f.kind) p.set("kind", f.kind);
    if (f.from) p.set("date_from", f.from);
    if (f.to) p.set("date_to", f.to);
    return call<Portfolio>(`/portfolio?${p}`);
  },
  refresh: () => call<{ prices: number; inflation: number; errors: number }>("/refresh", { method: "POST" }),
  inflation: () => call<Inflation[]>("/inflation"),
  addInflation: (body: { year: number; month: number; index: string }) =>
    call<Inflation>("/inflation", json("POST", body)),
  bondTypes: () => call<BondType[]>("/bond-types"),
};

export const INVESTMENTS_KEY = ["investments"];
