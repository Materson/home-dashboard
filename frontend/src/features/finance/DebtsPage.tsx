/**
 * Debts / IOUs — money given to or received from people, kept out of the
 * income/expense ledger. Everyone ever recorded stays on the list (settled
 * ones show 0); selecting a row shows its history and pre-fills "Who" when
 * adding a new entry. "Show settled" reveals the closed part of the history.
 */
import { useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Autocomplete,
  Badge,
  Button,
  Group,
  Modal,
  Paper,
  Popover,
  SegmentedControl,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isoDate, parseIsoDate } from "@/lib/format";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";

import { AmountInput, isPositiveAmount } from "@/components/AmountInput";

import { financeApi, type DebtBalance, type DebtDirection, type DebtEntryInput } from "./api";

const today = () => isoDate(new Date());
const sameName = (a: string | null, b: string) =>
  !!a && a.trim().toLowerCase() === b.trim().toLowerCase();

export function DebtsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [showSettled, setShowSettled] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const balances = useQuery({
    queryKey: ["finance", "debts", "balances", showSettled],
    queryFn: () => financeApi.debtBalances(showSettled),
  });
  const entries = useQuery({
    queryKey: ["finance", "debts", "entries", selected, showSettled],
    queryFn: () => financeApi.debtEntries(selected!, showSettled),
    enabled: !!selected,
  });
  const knownNames = useMemo(
    () => [...new Set((balances.data ?? []).map((b) => b.counterparty_name))],
    [balances.data],
  );

  const invalidate = () => qc.invalidateQueries({ queryKey: ["finance", "debts"] });
  const settle = useMutation({
    mutationFn: (b: DebtBalance) => financeApi.settleDebt(b.counterparty_name, b.currency, today()),
    onSuccess: invalidate,
  });
  const removePerson = useMutation({
    mutationFn: (name: string) => financeApi.deleteCounterparty(name),
    onSuccess: (_res, name) => {
      if (sameName(selected, name)) setSelected(null);
      invalidate();
    },
  });
  const removeEntry = useMutation({
    mutationFn: (id: string) => financeApi.deleteDebtEntry(id),
    onSuccess: invalidate,
  });

  return (
    <Stack gap="lg">
      <PageHeader
        title={t("debts.title")}
        subtitle={t("page.debts.subtitle")}
        actions={
          <>
            <Switch
              label={t("debts.showSettled")}
              checked={showSettled}
              onChange={(e) => setShowSettled(e.currentTarget.checked)}
            />
            <Button leftSection={<IconPlus size={16} />} onClick={() => setModalOpen(true)}>
              {t("debts.add")}
            </Button>
          </>
        }
      />

      <Paper withBorder p="md">
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("debts.col.who")}</Table.Th>
              <Table.Th ta="right">{t("debts.col.balance")}</Table.Th>
              <Table.Th>{t("debts.col.lastChange")}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(balances.data ?? []).map((b) => {
              const amount = Number(b.balance);
              const isSelected = sameName(selected, b.counterparty_name);
              return (
                <Table.Tr
                  key={`${b.counterparty_name.toLowerCase()}-${b.currency}`}
                  // Click selects (history + pre-filled "Who"); click again to clear.
                  onClick={() => setSelected(isSelected ? null : b.counterparty_name)}
                  style={{ cursor: "pointer" }}
                  bg={isSelected ? "var(--mantine-primary-color-light)" : undefined}
                  c={amount === 0 ? "dimmed" : undefined}
                >
                  <Table.Td>{b.counterparty_name}</Table.Td>
                  <Table.Td ta="right">
                    <Badge color={amount > 0 ? "teal" : amount < 0 ? "red" : "gray"} variant="light">
                      {Math.abs(amount).toFixed(2)} {b.currency}
                    </Badge>{" "}
                    <Text span size="xs" c="dimmed">
                      {amount > 0
                        ? t("debts.owesYou")
                        : amount < 0
                          ? t("debts.youOwe")
                          : t("debts.settled")}
                    </Text>
                  </Table.Td>
                  <Table.Td>{b.last_date}</Table.Td>
                  <Table.Td onClick={(e) => e.stopPropagation()}>
                    <Group justify="flex-end" gap="xs" wrap="nowrap">
                      {amount !== 0 && (
                        <Popover withArrow>
                          <Popover.Target>
                            <Button size="xs" variant="light">
                              {t("debts.settle")}
                            </Button>
                          </Popover.Target>
                          <Popover.Dropdown>
                            <Stack gap="xs">
                              <Text size="sm">
                                {t("debts.settleConfirm", {
                                  amount: Math.abs(amount).toFixed(2),
                                  currency: b.currency,
                                })}
                              </Text>
                              <Button
                                size="xs"
                                loading={settle.isPending}
                                onClick={() => settle.mutate(b)}
                              >
                                {t("debts.settle")}
                              </Button>
                            </Stack>
                          </Popover.Dropdown>
                        </Popover>
                      )}
                      <Popover withArrow>
                        <Popover.Target>
                          <ActionIcon
                            variant="subtle"
                            color="red"
                            aria-label={t("debts.removePerson")}
                          >
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Popover.Target>
                        <Popover.Dropdown>
                          <Stack gap="xs" maw={260}>
                            <Text size="sm">
                              {t("debts.removePersonConfirm", { name: b.counterparty_name })}
                            </Text>
                            <Button
                              size="xs"
                              color="red"
                              loading={removePerson.isPending}
                              onClick={() => removePerson.mutate(b.counterparty_name)}
                            >
                              {t("finance.action.delete")}
                            </Button>
                          </Stack>
                        </Popover.Dropdown>
                      </Popover>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              );
            })}
            {balances.isSuccess && !balances.data.length && (
              <Table.Tr>
                <Table.Td colSpan={4} ta="center" c="dimmed" py="md">
                  {t("debts.empty")}
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      {selected && (
        <Paper withBorder p="md">
          <Title order={5} mb="sm">
            {t("debts.history", { name: selected })}
          </Title>
          <Table striped>
            <Table.Tbody>
              {entries.isSuccess && !entries.data.length && (
                <Table.Tr>
                  <Table.Td c="dimmed">{t("debts.historyEmpty")}</Table.Td>
                </Table.Tr>
              )}
              {(entries.data ?? []).map((e) => (
                <Table.Tr key={e.id} c={e.settled ? "dimmed" : undefined}>
                  <Table.Td>{e.date}</Table.Td>
                  <Table.Td>{t(`debts.direction.${e.direction}`)}</Table.Td>
                  <Table.Td ta="right">
                    {e.amount} {e.currency}
                  </Table.Td>
                  <Table.Td>{e.due_date ? t("debts.dueOn", { date: e.due_date }) : ""}</Table.Td>
                  <Table.Td c="dimmed">
                    {e.settled ? `${t("debts.settled")}${e.notes ? " · " : ""}` : ""}
                    {e.notes}
                  </Table.Td>
                  <Table.Td>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label={t("finance.action.delete")}
                      onClick={() => removeEntry.mutate(e.id)}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}

      <DebtEntryModal
        opened={modalOpen}
        who={selected ?? ""}
        knownNames={knownNames}
        onClose={() => setModalOpen(false)}
        onSaved={(name) => {
          setSelected(name);
          invalidate();
        }}
      />
    </Stack>
  );
}

const DIRECTIONS: DebtDirection[] = ["gave", "received"];

function emptyForm(who: string): DebtEntryInput {
  return {
    counterparty_name: who,
    direction: "gave",
    amount: "",
    currency: "PLN",
    date: today(),
    due_date: null,
    notes: "",
  };
}

function DebtEntryModal(props: {
  opened: boolean;
  who: string;
  knownNames: string[];
  onClose: () => void;
  onSaved: (name: string) => void;
}) {
  const { t } = useTranslation();
  const [form, setForm] = useState<DebtEntryInput>(() => emptyForm(props.who));

  // Fresh form on every open, pre-filled with the selected person.
  useEffect(() => {
    if (props.opened) setForm(emptyForm(props.who));
  }, [props.opened, props.who]);

  const save = useMutation({
    mutationFn: () => financeApi.addDebtEntry(form),
    onSuccess: (entry) => {
      props.onSaved(entry.counterparty_name);
      props.onClose();
    },
  });

  return (
    <Modal opened={props.opened} onClose={props.onClose} title={t("debts.add")}>
      <Stack>
        <Autocomplete
          label={t("debts.field.who")}
          data={props.knownNames}
          value={form.counterparty_name}
          onChange={(v) => setForm({ ...form, counterparty_name: v })}
          data-autofocus={!props.who || undefined}
          required
        />
        <SegmentedControl
          fullWidth
          data={DIRECTIONS.map((d) => ({ value: d, label: t(`debts.direction.${d}`) }))}
          value={form.direction}
          onChange={(v) => setForm({ ...form, direction: v as DebtDirection })}
        />
        <Text size="xs" c="dimmed" mt={-8}>
          {t(`debts.directionHint.${form.direction}`)}
        </Text>
        <Group grow>
          <AmountInput
            label={t("finance.field.amount")}
            value={form.amount}
            onChange={(amount) => setForm({ ...form, amount })}
            data-autofocus={!!props.who || undefined}
            required
          />
          <TextInput
            label={t("finance.field.currency")}
            maxLength={3}
            value={form.currency}
            onChange={(e) => setForm({ ...form, currency: e.currentTarget.value.toUpperCase() })}
          />
        </Group>
        <Group grow>
          <DatePickerInput
            label={t("finance.field.date")}
            value={parseIsoDate(form.date)}
            onChange={(d) => setForm({ ...form, date: isoDate(d ?? new Date()) })}
          />
          <DatePickerInput
            label={t("debts.field.dueDate")}
            clearable
            value={form.due_date ? parseIsoDate(form.due_date) : null}
            onChange={(d) => setForm({ ...form, due_date: d ? isoDate(d) : null })}
          />
        </Group>
        <TextInput
          label={t("finance.field.notes")}
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.currentTarget.value })}
        />
        <Button
          onClick={() => save.mutate()}
          loading={save.isPending}
          disabled={!form.counterparty_name.trim() || !isPositiveAmount(form.amount)}
        >
          {t("finance.action.save")}
        </Button>
      </Stack>
    </Modal>
  );
}
