/**
 * Finance client — thin wrapper around fetch, so this module keeps working
 * before and after `npm run gen:api` creates the typed `paths` schema.
 * Once the OpenAPI client is more stable we can port these to `openapi-fetch`.
 */

export type Category = {
  id: string;
  key: string;
  name: string;
  kind: "expense" | "income" | "transfer";
  parent_id: string | null;
  color: string;
  is_system: boolean;
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
};

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
  if (!resp.ok) throw new Error(`${method} ${path} failed: ${resp.status}`);
  return (await resp.json()) as T;
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
  listTransactions: (f: TransactionFilters = {}) =>
    call<Transaction[]>(`/transactions${qs(f)}`),
  createTransaction: (body: Omit<Transaction, "id" | "recurring_rule_id" | "source_id">) =>
    call<Transaction>("/transactions", { method: "POST", body: JSON.stringify(body) }),
  updateTransaction: (id: string, body: Omit<Transaction, "id" | "recurring_rule_id" | "source_id"> & { update_future?: boolean }) =>
    call<Transaction>(`/transactions/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteTransaction: (id: string) => call<{ deleted: boolean }>(`/transactions/${id}`, { method: "DELETE" }),
  monthlyTotals: () => call<MonthlyTotal[]>("/monthly-totals"),

  listLoans: () => call<Loan[]>("/loans"),
  schedule: (id: string) => call<Schedule>(`/loans/${id}/schedule`),
  simulate: (id: string, extra: { date: string; amount: string; mode: "shorten_term" | "reduce_installment" }) =>
    call<OverpaymentComparison>(`/loans/${id}/simulate`, {
      method: "POST",
      body: JSON.stringify({ extra }),
    }),
};
