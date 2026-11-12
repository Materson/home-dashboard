/**
 * Repeating payments: what repeats, how often, the next date, who it's for.
 * ✎ changes the next occurrences; "Zakończ" stops it (what was already
 * recorded stays); a stopped one can be removed from the list. New ones are
 * made in the transaction form ("Powtarzaj").
 */
import { useState } from "react";
import { ActionIcon, Badge, Group, Modal, Table, Text, Tooltip } from "@mantine/core";
import { IconPencil, IconPlayerStop, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { Person } from "@/features/people/api";
import { fmtDate, fmtMoney } from "@/lib/format";

import { type Category, financeApi, type RecurringRule } from "./api";
import { RecurringEditModal } from "./RecurringEditModal";
import { repeatKind } from "./recurring";

export function RecurringModal(props: {
  opened: boolean;
  onClose: () => void;
  categoriesById: Record<string, Category>;
  peopleById: Record<string, Person>;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const rules = useQuery({
    queryKey: ["finance", "recurring"],
    queryFn: financeApi.listRecurring,
    enabled: props.opened,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["finance", "recurring"] });
  const stop = useMutation({ mutationFn: financeApi.stopRecurring, onSuccess: refresh });
  const remove = useMutation({ mutationFn: financeApi.deleteRecurring, onSuccess: refresh });
  const list = [...(rules.data ?? [])].sort((a, b) => Number(b.is_active) - Number(a.is_active));
  const [editing, setEditing] = useState<RecurringRule | null>(null);

  return (
    <Modal opened={props.opened} onClose={props.onClose} size="xl" title={t("finance.recurring.title")}>
      <Text size="sm" c="dimmed" mb="sm">
        {t("finance.recurring.hint")}
      </Text>
      <Table>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>{t("finance.field.name")}</Table.Th>
            <Table.Th>{t("finance.field.repeat")}</Table.Th>
            <Table.Th>{t("finance.recurring.next")}</Table.Th>
            <Table.Th>{t("finance.field.forWhom")}</Table.Th>
            <Table.Th ta="right">{t("finance.field.amount")}</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {list.map((r) => (
            <Table.Tr key={r.id} c={r.is_active ? undefined : "dimmed"}>
              <Table.Td>
                <Text size="sm" fw={500}>
                  {r.name}
                </Text>
                <Text size="xs" c="dimmed">
                  {props.categoriesById[r.category_id]?.name}
                </Text>
              </Table.Td>
              <Table.Td>{t(`finance.repeat.${repeatKind(r.rrule)}`)}</Table.Td>
              <Table.Td>
                {r.is_active ? (
                  fmtDate(r.next_run_at)
                ) : (
                  <Badge size="sm" color="gray">
                    {t("finance.recurring.stopped")}
                  </Badge>
                )}
                {r.is_active && r.end_date && (
                  <Text size="xs" c="dimmed">
                    {t("finance.recurring.until", { date: fmtDate(r.end_date) })}
                  </Text>
                )}
              </Table.Td>
              <Table.Td>
                {r.shares.length
                  ? r.shares.map((s) => props.peopleById[s.person_id]?.display_name ?? "…").join(", ")
                  : t("finance.field.forWhomShared")}
              </Table.Td>
              <Table.Td ta="right">{fmtMoney(r.amount, r.currency)}</Table.Td>
              <Table.Td>
                <Group gap={4} justify="flex-end" wrap="nowrap">
                  <Tooltip label={t("finance.action.edit")}>
                    <ActionIcon variant="subtle" onClick={() => setEditing(r)}>
                      <IconPencil size={16} />
                    </ActionIcon>
                  </Tooltip>
                  {r.is_active ? (
                    <Tooltip label={t("finance.recurring.stop")}>
                      <ActionIcon variant="subtle" color="orange" loading={stop.isPending && stop.variables === r.id} onClick={() => stop.mutate(r.id)}>
                        <IconPlayerStop size={16} />
                      </ActionIcon>
                    </Tooltip>
                  ) : (
                    <Tooltip label={t("finance.action.delete")}>
                      <ActionIcon variant="subtle" color="red" onClick={() => remove.mutate(r.id)}>
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Tooltip>
                  )}
                </Group>
              </Table.Td>
            </Table.Tr>
          ))}
          {rules.isSuccess && !list.length && (
            <Table.Tr>
              <Table.Td colSpan={6} c="dimmed" ta="center" py="md">
                {t("finance.recurring.empty")}
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
      <RecurringEditModal
        rule={editing}
        categories={Object.values(props.categoriesById)}
        onClose={() => setEditing(null)}
      />
    </Modal>
  );
}
