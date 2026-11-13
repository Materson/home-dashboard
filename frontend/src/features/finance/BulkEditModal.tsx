/**
 * Change who / the category on many transactions at once: the rows ticked
 * on the list, or everything its filters find (in the list's period — all
 * of it, not only the rows shown). Shows how many will change before saving.
 */
import { useEffect, useState } from "react";
import { Alert, Button, Group, Modal, Select, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { Person } from "@/features/people/api";

import { type BulkChange, type Category, financeApi, type TransactionFilters } from "./api";
import { categoryOptions } from "./categoryTree";
import { renderCategoryOption } from "./CategoryOption";

const KEEP = "keep";
const HOUSEHOLD = "household";

export function BulkEditModal(props: {
  opened: boolean;
  onClose: () => void;
  /** The list's filters (with its dates, if any). */
  filters: TransactionFilters;
  /** The list's period, as shown above it. */
  scope: string;
  /** Ticked rows; empty: everything the filters find. */
  ids: string[];
  categories: Category[];
  people: Person[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [person, setPerson] = useState<string>(KEEP); // KEEP | HOUSEHOLD | a person's id
  const [categoryId, setCategoryId] = useState<string | null>(null);
  useEffect(() => {
    if (!props.opened) return;
    setPerson(KEEP);
    setCategoryId(null);
  }, [props.opened]);

  const ticked = props.ids.length > 0;
  const body = (dryRun: boolean): BulkChange => ({
    filters: { ...props.filters, limit: undefined, offset: undefined },
    ids: ticked ? props.ids : undefined,
    person: person === KEEP || person === HOUSEHOLD ? person : "person",
    person_id: person === KEEP || person === HOUSEHOLD ? null : person,
    category_id: categoryId,
    dry_run: dryRun,
  });
  const count = useQuery({
    queryKey: ["finance", "bulk-count", body(true)],
    queryFn: () => financeApi.bulkUpdate(body(true)),
    enabled: props.opened,
  });
  const apply = useMutation({
    mutationFn: () => financeApi.bulkUpdate(body(false)),
    onSuccess: (r) => {
      notifications.show({ message: t("finance.bulk.done", { count: r.changed }) });
      qc.invalidateQueries({ queryKey: ["finance"] });
      props.onDone();
      props.onClose();
    },
  });
  const nothing = person === KEEP && !categoryId;
  const c = count.data;

  return (
    <Modal opened={props.opened} onClose={props.onClose} title={t("finance.bulk.title")}>
      <Stack>
        {ticked ? (
          <Text size="sm">{t("finance.bulk.ticked", { count: props.ids.length })}</Text>
        ) : (
          <Text size="sm">{t("finance.bulk.matching", { scope: props.scope })}</Text>
        )}
        <Select
          label={t("finance.field.forWhom")}
          allowDeselect={false}
          data={[
            { value: KEEP, label: t("finance.bulk.keep") },
            { value: HOUSEHOLD, label: t("finance.field.forWhomShared") },
            ...props.people.map((p) => ({ value: p.id, label: p.display_name })),
          ]}
          value={person}
          onChange={(v) => setPerson(v ?? KEEP)}
          description={person !== KEEP ? t("finance.bulk.splitHint") : undefined}
        />
        <Select
          label={t("finance.field.category")}
          placeholder={t("finance.bulk.keep")}
          clearable
          searchable
          data={(["expense", "income"] as const).map((kind) => ({
            group: t(`finance.chart.${kind}`),
            items: categoryOptions(props.categories.filter((cat) => cat.kind === kind), props.categories),
          }))}
          renderOption={renderCategoryOption}
          value={categoryId}
          onChange={setCategoryId}
        />
        {c && (
          <Text size="sm">
            {nothing ? t("finance.bulk.matched", { count: c.matched }) : t("finance.bulk.count", { matched: c.matched, changed: c.changed })}
          </Text>
        )}
        {c && c.wrong_kind > 0 && (
          <Text size="xs" c="orange">
            {t("finance.bulk.wrongKind", { count: c.wrong_kind })}
          </Text>
        )}
        {(count.isError || apply.isError) && <Alert color="red">{((count.error ?? apply.error) as Error).message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={props.onClose}>
            {t("finance.import.cancel")}
          </Button>
          <Button onClick={() => apply.mutate()} loading={apply.isPending} disabled={nothing || !c?.changed}>
            {t("finance.bulk.apply", { count: c?.changed ?? 0 })}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
