/**
 * TransactionModal — covers three cases:
 *
 *   • "new"       — empty form, Expense tab, today's date
 *   • "edit" tx   — fields prefilled from tx; calls PUT /transactions/{id}
 *                   and (when the tx came from a recurring rule) offers
 *                   "apply to future occurrences too?"
 *   • "duplicate" — fields prefilled from the source tx but the **date is
 *                   reset to today** and we create a new row on save
 *
 * The modal remounts whenever `mode`/`source` changes, so re-opening it
 * never shows stale values from the previous session.
 */
import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Checkbox,
  Modal,
  NumberInput,
  Select,
  Stack,
  Tabs,
  TextInput,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { financeApi, type Category, type Transaction } from "./api";

export type TxModalMode = "new" | "edit" | "duplicate";
export type TxModalSource = Transaction | null;
export type TxKind = "expense" | "income" | "transfer";

export function TransactionModal(props: {
  opened: boolean;
  onClose: () => void;
  categories: Category[];
  mode: TxModalMode;
  source: TxModalSource;
}) {
  const { opened, onClose, categories, mode, source } = props;
  const qc = useQueryClient();

  const categoriesById = useMemo(() => {
    const m: Record<string, Category> = {};
    categories.forEach((c) => (m[c.id] = c));
    return m;
  }, [categories]);

  const seedKind: TxKind =
    source && categoriesById[source.category_id]
      ? (categoriesById[source.category_id].kind as TxKind)
      : "expense";

  const [kind, setKind] = useState<TxKind>(seedKind);
  const [form, setForm] = useState(() => buildInitial(mode, source, seedKind));
  const [applyToFuture, setApplyToFuture] = useState(false);

  // Remount the form state whenever the modal transitions open / mode / source changes.
  useEffect(() => {
    if (!opened) return;
    const nextKind: TxKind =
      source && categoriesById[source.category_id]
        ? (categoriesById[source.category_id].kind as TxKind)
        : "expense";
    setKind(nextKind);
    setForm(buildInitial(mode, source, nextKind));
    setApplyToFuture(false);
  }, [opened, mode, source, categoriesById]);

  const categoriesForKind = useMemo(
    () => categories.filter((c) => c.kind === kind),
    [categories, kind],
  );

  function switchKind(next: TxKind) {
    setKind(next);
    setForm((f) => ({ ...f, category_id: "" }));
  }

  const create = useMutation({
    mutationFn: () => financeApi.createTransaction(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance"] });
      onClose();
    },
  });
  const update = useMutation({
    mutationFn: () =>
      financeApi.updateTransaction(source!.id, { ...form, update_future: applyToFuture }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance"] });
      onClose();
    },
  });

  const title =
    mode === "edit" ? "Edit transaction" : mode === "duplicate" ? "Duplicate transaction" : "Add transaction";
  const saving = create.isPending || update.isPending;
  const isRecurring = mode === "edit" && !!source?.recurring_rule_id;

  function save() {
    if (mode === "edit") update.mutate();
    else create.mutate();
  }

  function renderForm() {
    return (
      <Stack mt="md">
        <TextInput
          label="Name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
          required
        />
        <NumberInput
          label="Amount"
          decimalScale={2}
          fixedDecimalScale
          value={Number(form.amount)}
          onChange={(v) => setForm({ ...form, amount: String(v ?? 0) })}
          min={0}
        />
        <TextInput
          label="Currency"
          value={form.currency}
          onChange={(e) => setForm({ ...form, currency: e.currentTarget.value.toUpperCase() })}
          maxLength={3}
        />
        <DatePickerInput
          label="Date"
          value={new Date(form.date)}
          onChange={(d) => setForm({ ...form, date: (d ?? new Date()).toISOString().slice(0, 10) })}
        />
        <Select
          label="Category"
          placeholder={
            categoriesForKind.length
              ? "Pick one"
              : `No ${kind} categories yet — add one under Settings`
          }
          data={categoriesForKind.map((c) => ({ value: c.id, label: c.name }))}
          value={form.category_id}
          onChange={(v) => setForm({ ...form, category_id: v ?? "" })}
          searchable
          required
          disabled={!categoriesForKind.length}
        />
        <TextInput
          label="Notes"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.currentTarget.value })}
        />
        {isRecurring && (
          <Checkbox
            label="Apply changes to future occurrences too"
            checked={applyToFuture}
            onChange={(e) => setApplyToFuture(e.currentTarget.checked)}
          />
        )}
        <Button onClick={save} loading={saving} disabled={!form.category_id || !form.name}>
          {mode === "edit" ? "Save changes" : "Save"}
        </Button>
      </Stack>
    );
  }

  return (
    <Modal opened={opened} onClose={onClose} title={title} keepMounted={false}>
      <Tabs value={kind} onChange={(v) => v && switchKind(v as TxKind)} keepMounted={false}>
        <Tabs.List grow>
          <Tabs.Tab value="expense" color="red">
            Expense
          </Tabs.Tab>
          <Tabs.Tab value="income" color="teal">
            Income
          </Tabs.Tab>
          <Tabs.Tab value="transfer" color="gray">
            Transfer
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="expense">{renderForm()}</Tabs.Panel>
        <Tabs.Panel value="income">{renderForm()}</Tabs.Panel>
        <Tabs.Panel value="transfer">{renderForm()}</Tabs.Panel>
      </Tabs>
    </Modal>
  );
}

function buildInitial(mode: TxModalMode, source: TxModalSource, _kind: TxKind) {
  const today = new Date().toISOString().slice(0, 10);
  if (mode === "new" || !source) {
    return {
      date: today,
      amount: "0.00",
      currency: "PLN",
      category_id: "",
      person_id: null as string | null,
      name: "",
      notes: "",
    };
  }
  return {
    date: mode === "duplicate" ? today : source.date,
    amount: source.amount,
    currency: source.currency,
    category_id: source.category_id,
    person_id: source.person_id,
    name: source.name,
    notes: source.notes,
  };
}
