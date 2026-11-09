import { useMemo, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  MultiSelect,
  NumberInput,
  Paper,
  Stack,
  Table,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { MonthPickerInput } from "@mantine/dates";
import { IconCopy, IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { financeApi, type Category, type Transaction, type TransactionFilters } from "./api";
import { MonthlyChart } from "./MonthlyChart";
import { TransactionModal, type TxModalMode, type TxModalSource } from "./TransactionModal";

/**
 * Finance page — month-scoped list of transactions with per-month totals,
 * monthly chart, and add / edit / duplicate controls. The default month is
 * the current one; use the month picker at the top to move through history.
 */
export function FinancePage() {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const [month, setMonth] = useState<Date>(() => firstOfMonth(new Date()));
  const [search, setSearch] = useState<{
    q: string;
    amount_min: string | undefined;
    amount_max: string | undefined;
    category_ids: string[];
  }>({ q: "", amount_min: undefined, amount_max: undefined, category_ids: [] });

  const [modalMode, setModalMode] = useState<TxModalMode>("new");
  const [modalSource, setModalSource] = useState<TxModalSource>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const categoriesQ = useQuery({
    queryKey: ["finance", "categories"],
    queryFn: () => financeApi.listCategories(),
  });
  const categoriesById = useMemo(() => {
    const m: Record<string, Category> = {};
    (categoriesQ.data ?? []).forEach((c) => (m[c.id] = c));
    return m;
  }, [categoriesQ.data]);

  const filters: TransactionFilters = useMemo(() => {
    const { date_from, date_to } = monthRange(month);
    const category_keys = search.category_ids
      .map((id) => categoriesById[id]?.key)
      .filter((k): k is string => !!k);
    return {
      date_from,
      date_to,
      limit: 500,
      q: search.q || undefined,
      amount_min: search.amount_min,
      amount_max: search.amount_max,
      category_keys: category_keys.length ? category_keys : undefined,
    };
  }, [month, search, categoriesById]);

  const transactionsQ = useQuery({
    queryKey: ["finance", "transactions", filters],
    queryFn: () => financeApi.listTransactions(filters),
  });
  const totalsQ = useQuery({
    queryKey: ["finance", "monthly-totals"],
    queryFn: () => financeApi.monthlyTotals(),
  });

  const monthTotals = useMemo(
    () => summarize(transactionsQ.data ?? [], categoriesById),
    [transactionsQ.data, categoriesById],
  );

  const del = useMutation({
    mutationFn: (id: string) => financeApi.deleteTransaction(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["finance"] }),
  });

  function openNew() {
    setModalMode("new");
    setModalSource(null);
    setModalOpen(true);
  }
  function openEdit(tx: Transaction) {
    setModalMode("edit");
    setModalSource(tx);
    setModalOpen(true);
  }
  function openDuplicate(tx: Transaction) {
    setModalMode("duplicate");
    setModalSource(tx);
    setModalOpen(true);
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group>
          <Title order={2}>{t("nav.finance")}</Title>
          <MonthPickerInput
            value={month}
            onChange={(d) => d && setMonth(firstOfMonth(d))}
            valueFormat="MMMM YYYY"
            w={200}
          />
        </Group>
        <Group>
          <Badge color="teal" size="lg">
            Income: {monthTotals.income.toFixed(2)}
          </Badge>
          <Badge color="red" size="lg">
            Expense: {monthTotals.expense.toFixed(2)}
          </Badge>
          <Badge color="gray" size="lg">
            Net: {(monthTotals.income - monthTotals.expense).toFixed(2)}
          </Badge>
          <Button leftSection={<IconPlus size={16} />} onClick={openNew}>
            Add transaction
          </Button>
        </Group>
      </Group>

      {categoriesQ.isError && <Alert color="red">{t("common.noAccess")}</Alert>}

      <MonthlyChart totals={totalsQ.data ?? []} />

      <Paper withBorder p="md">
        <Group gap="xs" wrap="wrap" mb="sm">
          <TextInput
            placeholder="Search name / notes"
            value={search.q}
            onChange={(e) => setSearch({ ...search, q: e.currentTarget.value })}
            w={240}
          />
          <NumberInput
            placeholder="Min"
            value={search.amount_min ? Number(search.amount_min) : undefined}
            onChange={(v) => setSearch({ ...search, amount_min: v ? String(v) : undefined })}
            w={120}
            min={0}
          />
          <NumberInput
            placeholder="Max"
            value={search.amount_max ? Number(search.amount_max) : undefined}
            onChange={(v) => setSearch({ ...search, amount_max: v ? String(v) : undefined })}
            w={120}
            min={0}
          />
          <MultiSelect
            placeholder="Category"
            data={(categoriesQ.data ?? []).map((c) => ({
              value: c.id,
              label: `${c.name} (${c.kind})`,
            }))}
            value={search.category_ids}
            onChange={(ids) => setSearch({ ...search, category_ids: ids })}
            searchable
            clearable
            w={320}
          />
        </Group>

        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Date</Table.Th>
              <Table.Th>Name</Table.Th>
              <Table.Th>Category</Table.Th>
              <Table.Th ta="right">Amount</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(transactionsQ.data ?? []).map((tx: Transaction) => {
              const cat = categoriesById[tx.category_id];
              return (
                <Table.Tr key={tx.id}>
                  <Table.Td>{tx.date}</Table.Td>
                  <Table.Td>{tx.name}</Table.Td>
                  <Table.Td>{cat?.name ?? tx.category_id.slice(0, 8)}</Table.Td>
                  <Table.Td ta="right" c={cat?.kind === "income" ? "teal" : undefined}>
                    {tx.amount} {tx.currency}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <Tooltip label="Edit">
                        <ActionIcon variant="subtle" onClick={() => openEdit(tx)}>
                          <IconPencil size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label="Duplicate (today's date)">
                        <ActionIcon variant="subtle" onClick={() => openDuplicate(tx)}>
                          <IconCopy size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label="Delete">
                        <ActionIcon variant="subtle" color="red" onClick={() => del.mutate(tx.id)}>
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              );
            })}
            {!transactionsQ.isLoading && !(transactionsQ.data ?? []).length && (
              <Table.Tr>
                <Table.Td colSpan={5} ta="center" c="dimmed" py="md">
                  No transactions in this month.
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      <TransactionModal
        opened={modalOpen}
        onClose={() => setModalOpen(false)}
        categories={categoriesQ.data ?? []}
        mode={modalMode}
        source={modalSource}
      />
    </Stack>
  );
}

// ---- helpers ----

function firstOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function monthRange(d: Date): { date_from: string; date_to: string } {
  const start = new Date(d.getFullYear(), d.getMonth(), 1);
  const end = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  return { date_from: iso(start), date_to: iso(end) };
}

function iso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function summarize(
  txs: Transaction[],
  categoriesById: Record<string, Category>,
): { income: number; expense: number } {
  let income = 0;
  let expense = 0;
  for (const tx of txs) {
    const cat = categoriesById[tx.category_id];
    if (!cat) continue;
    const amount = Number(tx.amount);
    if (cat.kind === "income") income += amount;
    else if (cat.kind === "expense") expense += amount;
  }
  return { income, expense };
}
