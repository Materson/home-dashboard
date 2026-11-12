/**
 * Finance client — thin wrapper around fetch, so this module keeps working
 * before and after `npm run gen:api` creates the typed `paths` schema.
 * Once the OpenAPI client is more stable we can port these to `openapi-fetch`.
 */

import type { Share } from "./shares";

export type { Share };
export type Repeat = "" | "weekly" | "monthly" | "quarterly" | "yearly";

export type Category = {
  id: string;
  key: string;
  name: string;
  kind: "expense" | "income" | "transfer";
  parent_id: string | null;
  color: string;
  is_system: boolean;
  /** Transactions in it. */
  used: number;
};

export type Transaction = {
  id: string;
  date: string;              // ISO (YYYY-MM-DD)
  amount: string;            // Decimal rendered as string by Ninja
  currency: string;
  name: string;
  notes: string;
  category_id: string;
  person_id: string | null;
  recurring_rule_id: string | null;
  source_id: string | null;
  /** What it was for, e.g. "health.cabinetitem" + a medicine id ("" / null = nothing). */
  related_kind: string;
  related_id: string | null;
  /** Who it was for, split; empty = the household. */
  shares: Share[];
};

/** What the form sends: a transaction, optionally repeating from its date. */
export type TransactionInput = Omit<Transaction, "id" | "recurring_rule_id" | "source_id"> & {
  repeat?: Repeat;
  repeat_until?: string | null;
};

export type RecurringRule = {
  id: string;
  name: string;
  amount: string;
  currency: string;
  category_id: string;
  person_id: string | null;
  rrule: string;
  start_date: string;
  end_date: string | null;
  next_run_at: string;
  is_active: boolean;
  shares: Share[];
  notes: string;
};

/** Editing a repeating payment changes its next occurrences. */
export type RecurringEdit = {
  name: string;
  amount: string;
  currency: string;
  category_id: string;
  notes: string;
  end_date: string | null;
  shares: Share[];
  repeat: Repeat;
};

/** A pie slice: a category or a person ("shared" = the household). */
export type Slice = { key: string; label: string; color: string; total: string };

export type TransactionFilters = {
  q?: string;
  date_from?: string;
  date_to?: string;
  amount_min?: string;
  amount_max?: string;
  category_keys?: string[];
  person_ids?: string[];
  kind?: "expense" | "income" | "transfer";
  limit?: number;
  offset?: number;
};

export type MonthlyTotal = {
  year_month: string;        // YYYY-MM
  kind: "expense" | "income" | "transfer";
  total: string;
  currency: string;
};

export type Loan = {
  id: string;
  name: string;
  person_id: string | null;
  kind: string;
  principal: string;
  currency: string;
  start_date: string;
  term_months: number;
  base_rate: string;
};

export type InstallmentRow = {
  index: number;
  due_date: string;
  opening_balance: string;
  installment: string;
  principal_part: string;
  interest_part: string;
  overpayment: string;
  closing_balance: string;
  nominal_rate_p_a: string;
};

export type Schedule = {
  rows: InstallmentRow[];
  total_installments: string;
  total_interest: string;
  total_overpayment: string;
  months: number;
};

export type OverpaymentComparison = {
  base: Schedule;
  with_overpayment: Schedule;
  saved_interest: string;
  months_saved: number;
};

export type Bookmark = {
  id: string;
  label: string;
  name: string;
  amount: string;
  currency: string;
  category_id: string;
  person_id: string | null;
  notes: string;
  sort_order: number;
  shares: Share[];
};
export type BookmarkInput = Omit<Bookmark, "id" | "sort_order"> & { sort_order?: number };

/** gave: money went to them (a loan or a repayment); received: the reverse. */
export type DebtDirection = "gave" | "received";

export type DebtEntry = {
  id: string;
  /** "Who" — plain text, matched case-insensitively. */
  counterparty_name: string;
  direction: DebtDirection;
  amount: string;
  currency: string;
  date: string;
  due_date: string | null;
  notes: string;
  /** Part of a closed period (the balance reached zero afterwards). */
  settled?: boolean;
};
export type DebtEntryInput = Omit<DebtEntry, "id" | "settled">;

export type DebtBalance = {
  counterparty_name: string;
  currency: string;
  balance: string; // > 0 they owe us, < 0 we owe them, 0 settled
  entries: number;
  last_date: string;
};

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (unsafe) headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api/finance" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) {
    // The server explains what's wrong (e.g. "the category is in use") — show that.
    const body = (await resp.json().catch(() => ({}))) as { detail?: unknown };
    throw new Error(typeof body.detail === "string" ? body.detail : `${method} ${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

/** Like `call`, for endpoints that may answer 204 No Content. */
async function callNoContent(path: string, init: RequestInit = {}): Promise<void> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api/finance" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) throw new Error(`${init.method ?? "GET"} ${path} failed: ${resp.status}`);
}

function qs(f: TransactionFilters): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)));
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const financeApi = {
  listCategories: () => call<Category[]>("/categories"),
  createCategory: (body: { name: string; kind: "expense" | "income"; color: string; parent_id?: string | null }) =>
    call<Category>("/categories", { method: "POST", body: JSON.stringify(body) }),
  /** ``parent_id: null`` makes it a main category. */
  updateCategory: (id: string, body: { name: string; color: string; parent_id: string | null }) =>
    call<Category>(`/categories/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  mergeCategory: (id: string, into: string) =>
    call<{ moved: number }>(`/categories/${id}/merge`, { method: "POST", body: JSON.stringify({ into }) }),
  deleteCategory: (id: string) => call<{ deleted: boolean }>(`/categories/${id}`, { method: "DELETE" }),
  listTransactions: (f: TransactionFilters = {}) =>
    call<Transaction[]>(`/transactions${qs(f)}`),
  createTransaction: (body: TransactionInput) =>
    call<Transaction>("/transactions", { method: "POST", body: JSON.stringify(body) }),
  updateTransaction: (id: string, body: TransactionInput & { update_future?: boolean }) =>
    call<Transaction>(`/transactions/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteTransaction: (id: string) => call<{ deleted: boolean }>(`/transactions/${id}`, { method: "DELETE" }),
  monthlyTotals: (until: string, months = 12, person?: string | null) =>
    call<MonthlyTotal[]>(
      `/monthly-totals?until=${until}&months=${months}${person ? `&person=${person}` : ""}`,
    ),
  /** Per main category; with ``parent``, that main category per sub-category. */
  categoryTotals: (
    from: string,
    to: string,
    kind: "income" | "expense",
    person?: string | null,
    parent?: string | null,
  ) =>
    call<Slice[]>(
      `/category-totals?date_from=${from}&date_to=${to}&kind=${kind}` +
        `${person ? `&person=${person}` : ""}${parent ? `&parent=${parent}` : ""}`,
    ),
  personTotals: (from: string, to: string, kind: "income" | "expense") =>
    call<Slice[]>(`/person-totals?date_from=${from}&date_to=${to}&kind=${kind}`),

  listRecurring: () => call<RecurringRule[]>("/recurring"),
  updateRecurring: (id: string, body: RecurringEdit) =>
    call<RecurringRule>(`/recurring/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  stopRecurring: (id: string) => call<RecurringRule>(`/recurring/${id}/stop`, { method: "POST" }),
  deleteRecurring: (id: string) => call<{ deleted: boolean }>(`/recurring/${id}`, { method: "DELETE" }),

  listLoans: () => call<Loan[]>("/loans"),
  schedule: (id: string) => call<Schedule>(`/loans/${id}/schedule`),
  simulate: (id: string, extra: { date: string; amount: string; mode: "shorten_term" | "reduce_installment" }) =>
    call<OverpaymentComparison>(`/loans/${id}/simulate`, {
      method: "POST",
      body: JSON.stringify({ extra }),
    }),
  listBookmarks: () => call<Bookmark[]>("/bookmarks"),
  createBookmark: (body: BookmarkInput) =>
    call<Bookmark>("/bookmarks", { method: "POST", body: JSON.stringify(body) }),
  deleteBookmark: (id: string) => call<{ deleted: boolean }>(`/bookmarks/${id}`, { method: "DELETE" }),

  debtBalances: (includeSettled: boolean) =>
    call<DebtBalance[]>(`/debts/balances?include_settled=${includeSettled}`),
  debtEntries: (name: string, includeSettled: boolean) =>
    call<DebtEntry[]>(
      `/debts/entries?name=${encodeURIComponent(name)}&include_settled=${includeSettled}`,
    ),
  addDebtEntry: (body: DebtEntryInput) =>
    call<DebtEntry>("/debts/entries", { method: "POST", body: JSON.stringify(body) }),
  deleteDebtEntry: (id: string) =>
    call<{ deleted: boolean }>(`/debts/entries/${id}`, { method: "DELETE" }),
  /** Removes the person and every entry recorded for them. */
  deleteCounterparty: (name: string) =>
    call<{ deleted: number }>(`/debts/counterparty?name=${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
  settleDebt: (name: string, currency: string, date: string) =>
    callNoContent("/debts/settle", {
      method: "POST",
      body: JSON.stringify({ name, currency, date }),
    }),
};
