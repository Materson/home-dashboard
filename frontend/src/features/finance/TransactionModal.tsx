/**
 * TransactionModal — covers three cases:
 *
 *   • "new"       — empty form, Expense tab, today's date
 *   • "edit" tx   — fields prefilled from tx; calls PUT /transactions/{id}
 *                   and (when the tx came from a recurring rule) offers
 *                   "apply to future occurrences too?"
 *   • "duplicate" — fields prefilled from the source tx but the **date is
 *                   reset to today** and we create a new row on save
 *   • "bookmark"  — same as duplicate, the source being a saved bookmark
 *
 * The modal remounts whenever `mode`/`source` changes, so re-opening it
 * never shows stale values from the previous session.
 */
import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Group,
  Modal,
  Paper,
  Select,
  Stack,
  Tabs,
  Text,
  TextInput,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AmountInput, isPositiveAmount } from "@/components/AmountInput";
import { isoDate, parseIsoDate } from "@/lib/format";

import { cabinetApi } from "@/features/health/api";

import { financeApi, type Category, type Repeat, type Transaction } from "./api";
import { categoryOptions, mainOf } from "./categoryTree";
import { renderCategoryOption } from "./CategoryOption";
import { type Share, sharesValid } from "./shares";
import { SharesEditor } from "./SharesEditor";

const REPEATS: Repeat[] = ["", "weekly", "monthly", "quarterly", "yearly"];

const MEDICINE_KIND = "health.cabinetitem";

export type TxModalMode = "new" | "edit" | "duplicate" | "bookmark";
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
  const { t } = useTranslation();

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
  // Editing one occurrence of a repeating payment: ask "only this / all following".
  const [askScope, setAskScope] = useState(false);

  // Remount the form state whenever the modal transitions open / mode / source changes.
  useEffect(() => {
    if (!opened) return;
    const nextKind: TxKind =
      source && categoriesById[source.category_id]
        ? (categoriesById[source.category_id].kind as TxKind)
        : "expense";
    setKind(nextKind);
    setForm(buildInitial(mode, source, nextKind));
    setAskScope(false);
  }, [opened, mode, source, categoriesById]);

  // Health purchases (e.g. medicines bought at the pharmacy) can be linked to
  // a cabinet medicine, so the medicine shows what was paid for it.
  // (also a sub-category someone added under Zdrowie)
  const picked = categoriesById[form.category_id];
  const isHealthCategory =
    !!picked && [picked.key, mainOf(picked, categoriesById).key].some((k) => k.startsWith("health"));
  const cabinet = useQuery({
    queryKey: ["cabinet", "", "all", false],
    queryFn: () => cabinetApi.list("", "all", false),
    enabled: opened && isHealthCategory,
  });
  const medicines = (cabinet.data ?? []).map((i) => ({ value: i.id, label: i.name }));

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
      qc.invalidateQueries({ queryKey: ["cabinet"] });
      onClose();
    },
  });
  const update = useMutation({
    mutationFn: (future: boolean) =>
      financeApi.updateTransaction(source!.id, {
        ...form,
        repeat: "",
        repeat_until: null,
        update_future: future,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance"] });
      onClose();
    },
  });

  const saveError = (create.error ?? update.error) as Error | null;

  const title = t(
    mode === "edit" ? "finance.tx.edit" : mode === "duplicate" ? "finance.tx.duplicate" : "finance.tx.add",
  );
  const saving = create.isPending || update.isPending;
  const isRecurring = mode === "edit" && !!source?.recurring_rule_id;

  function save() {
    if (mode !== "edit") create.mutate();
    else if (isRecurring) setAskScope(true);
    else update.mutate(false);
  }
  const startsInPast = mode !== "edit" && !!form.repeat && form.date < isoDate(new Date());

  function renderForm() {
    return (
      <Stack mt="md">
        <TextInput
          label={t("finance.field.name")}
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
          required
        />
        <AmountInput
          label={t("finance.field.amount")}
          value={form.amount}
          onChange={(amount) => setForm({ ...form, amount })}
          required
        />
        <TextInput
          label={t("finance.field.currency")}
          value={form.currency}
          onChange={(e) => setForm({ ...form, currency: e.currentTarget.value.toUpperCase() })}
          maxLength={3}
        />
        <DatePickerInput
          label={t("finance.field.date")}
          value={parseIsoDate(form.date)}
          // Local date — toISOString() would be the previous day in Poland (UTC+1/+2).
          onChange={(d) => setForm({ ...form, date: isoDate(d ?? new Date()) })}
        />
        <Select
          label={t("finance.field.category")}
          placeholder={t(
            categoriesForKind.length ? "finance.field.categoryPick" : "finance.field.categoryNone",
          )}
          data={categoryOptions(categoriesForKind)}
          renderOption={renderCategoryOption}
          value={form.category_id}
          onChange={(v) => setForm({ ...form, category_id: v ?? "" })}
          searchable
          required
          disabled={!categoriesForKind.length}
        />
        {isHealthCategory && medicines.length > 0 && (
          <Select
            label={t("finance.field.medicine")}
            description={t("finance.field.medicineHint")}
            placeholder={t("finance.field.medicinePick")}
            data={medicines}
            value={form.related_kind === MEDICINE_KIND ? form.related_id : null}
            onChange={(v) =>
              setForm({ ...form, related_kind: v ? MEDICINE_KIND : "", related_id: v })
            }
            searchable
            clearable
          />
        )}
        <SharesEditor
          amount={form.amount}
          currency={form.currency}
          value={form.shares}
          onChange={(shares) => setForm((f) => ({ ...f, shares }))}
        />
        {mode !== "edit" && (
          <Group grow align="flex-start">
            <Select
              label={t("finance.field.repeat")}
              allowDeselect={false}
              data={REPEATS.map((r) => ({ value: r, label: t(`finance.repeat.${r || "none"}`) }))}
              value={form.repeat}
              onChange={(v) => setForm((f) => ({ ...f, repeat: (v ?? "") as Repeat }))}
            />
            {form.repeat && (
              <DatePickerInput
                label={t("finance.field.repeatUntil")}
                placeholder={t("finance.field.repeatForever")}
                clearable
                value={form.repeat_until ? parseIsoDate(form.repeat_until) : null}
                onChange={(d) => setForm((f) => ({ ...f, repeat_until: d ? isoDate(d) : null }))}
              />
            )}
          </Group>
        )}
        {startsInPast && (
          <Text size="xs" c="dimmed">
            {t("finance.recurring.backfillHint")}
          </Text>
        )}
        <TextInput
          label={t("finance.field.notes")}
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.currentTarget.value })}
        />
        {saveError && (
          <Text size="sm" c="red">
            {t("common.saveFailed")}
          </Text>
        )}
        {askScope ? (
          <Paper withBorder p="sm" bg="var(--mantine-color-blue-light)">
            <Stack gap="xs">
              <Text size="sm" fw={500}>
                {t("finance.recurring.scopeQuestion")}
              </Text>
              <Group gap="xs">
                <Button size="xs" variant="default" loading={update.isPending && update.variables === false} onClick={() => update.mutate(false)}>
                  {t("finance.recurring.onlyThis")}
                </Button>
                <Button size="xs" loading={update.isPending && update.variables === true} onClick={() => update.mutate(true)}>
                  {t("finance.recurring.thisAndFollowing")}
                </Button>
                <Button size="xs" variant="subtle" color="gray" onClick={() => setAskScope(false)}>
                  {t("notes.cancel")}
                </Button>
              </Group>
            </Stack>
          </Paper>
        ) : (
        <Button
          onClick={save}
          loading={saving}
          disabled={
            !form.category_id ||
            !form.name ||
            !isPositiveAmount(form.amount) ||
            !sharesValid(form.amount, form.shares)
          }
        >
          {t(mode === "edit" ? "finance.action.saveChanges" : "finance.action.save")}
        </Button>
        )}
      </Stack>
    );
  }

  return (
    <Modal opened={opened} onClose={onClose} title={title} keepMounted={false}>
      <Tabs value={kind} onChange={(v) => v && switchKind(v as TxKind)} keepMounted={false}>
        <Tabs.List grow>
          <Tabs.Tab value="expense" color="red">
            {t("finance.kind.expense")}
          </Tabs.Tab>
          <Tabs.Tab value="income" color="teal">
            {t("finance.kind.income")}
          </Tabs.Tab>
          {kind === "transfer" && (
            <Tabs.Tab value="transfer" color="gray">
              {t("finance.kind.transfer")}
            </Tabs.Tab>
          )}
        </Tabs.List>

        <Tabs.Panel value="expense">{renderForm()}</Tabs.Panel>
        <Tabs.Panel value="income">{renderForm()}</Tabs.Panel>
        <Tabs.Panel value="transfer">{renderForm()}</Tabs.Panel>
      </Tabs>
    </Modal>
  );
}

function buildInitial(mode: TxModalMode, source: TxModalSource, _kind: TxKind) {
  const today = isoDate(new Date());
  if (mode === "new" || !source) {
    return {
      date: today,
      amount: "",
      currency: "PLN",
      category_id: "",
      person_id: null as string | null,
      name: "",
      notes: "",
      related_kind: "",
      related_id: null as string | null,
      shares: [] as Share[],
      repeat: "" as Repeat,
      repeat_until: null as string | null,
    };
  }
  return {
    // Duplicates and bookmarks are new entries happening now.
    date: mode === "edit" ? source.date : today,
    amount: source.amount,
    currency: source.currency,
    category_id: source.category_id,
    person_id: source.person_id,
    related_kind: source.related_kind ?? "",
    related_id: source.related_id ?? null,
    name: source.name,
    notes: source.notes,
    // Older entries (and bookmarks) may only name one person.
    shares:
      source.shares?.length
        ? source.shares
        : source.person_id
          ? [{ person_id: source.person_id, amount: source.amount }]
          : [],
    repeat: "" as Repeat,
    repeat_until: null as string | null,
  };
}
