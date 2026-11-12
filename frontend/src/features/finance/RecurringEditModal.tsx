/**
 * Edit a repeating payment from the list: name, amount, category, who it's
 * for (split), how often, until when. Applies to the next occurrences —
 * the ones already recorded stay as they are (edit those one by one, or
 * "this and all following" from the transaction itself).
 */
import { useEffect, useState } from "react";
import { Alert, Button, Group, Modal, Select, Stack, Text, TextInput } from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { AmountInput, isPositiveAmount } from "@/components/AmountInput";
import { isoDate, parseIsoDate } from "@/lib/format";

import { type Category, financeApi, type RecurringEdit, type RecurringRule, type Repeat } from "./api";
import { repeatKind } from "./recurring";
import { sharesValid } from "./shares";
import { SharesEditor } from "./SharesEditor";

const REPEATS: Repeat[] = ["weekly", "monthly", "quarterly", "yearly"];

export function RecurringEditModal(props: { rule: RecurringRule | null; categories: Category[]; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const rule = props.rule;
  const [form, setForm] = useState<RecurringEdit | null>(null);

  useEffect(() => {
    if (!rule) return;
    const kind = repeatKind(rule.rrule);
    setForm({
      name: rule.name,
      amount: rule.amount,
      currency: rule.currency,
      category_id: rule.category_id,
      notes: rule.notes,
      end_date: rule.end_date,
      shares: rule.shares,
      repeat: (REPEATS as string[]).includes(kind) ? (kind as Repeat) : "",
    });
  }, [rule]);

  const save = useMutation({
    mutationFn: () => financeApi.updateRecurring(rule!.id, form!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance"] });
      props.onClose();
    },
  });
  const kind = props.categories.find((c) => c.id === rule?.category_id)?.kind;
  const categories = props.categories.filter((c) => c.kind === kind);

  return (
    <Modal opened={!!rule} onClose={props.onClose} title={t("finance.recurring.edit")}>
      {form && (
        <Stack>
          <Text size="xs" c="dimmed">
            {t("finance.recurring.editHint")}
          </Text>
          <TextInput label={t("finance.field.name")} value={form.name} onChange={(e) => setForm({ ...form, name: e.currentTarget.value })} />
          <Group grow align="flex-start">
            <AmountInput label={t("finance.field.amount")} value={form.amount} onChange={(amount) => setForm({ ...form, amount })} />
            <Select
              label={t("finance.field.category")}
              data={categories.map((c) => ({ value: c.id, label: c.name }))}
              value={form.category_id}
              onChange={(v) => v && setForm({ ...form, category_id: v })}
              allowDeselect={false}
              searchable
            />
          </Group>
          <SharesEditor
            amount={form.amount}
            currency={form.currency}
            value={form.shares}
            onChange={(shares) => setForm((f) => (f ? { ...f, shares } : f))}
          />
          <Group grow align="flex-start">
            <Select
              label={t("finance.field.repeat")}
              description={t("finance.recurring.frequencyHint")}
              allowDeselect={false}
              data={REPEATS.map((r) => ({ value: r, label: t(`finance.repeat.${r}`) }))}
              value={form.repeat || null}
              onChange={(v) => setForm({ ...form, repeat: (v ?? "") as Repeat })}
            />
            <DatePickerInput
              label={t("finance.field.repeatUntil")}
              placeholder={t("finance.field.repeatForever")}
              clearable
              value={form.end_date ? parseIsoDate(form.end_date) : null}
              onChange={(d) => setForm({ ...form, end_date: d ? isoDate(d) : null })}
            />
          </Group>
          <TextInput label={t("finance.field.notes")} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.currentTarget.value })} />
          {save.isError && <Alert color="red">{t("common.saveFailed")}</Alert>}
          <Button
            onClick={() => save.mutate()}
            loading={save.isPending}
            disabled={!form.name.trim() || !isPositiveAmount(form.amount) || !sharesValid(form.amount, form.shares)}
          >
            {t("finance.action.saveChanges")}
          </Button>
        </Stack>
      )}
    </Modal>
  );
}
