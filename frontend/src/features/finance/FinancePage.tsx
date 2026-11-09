import { useMemo, useState } from "react";
import {
  ActionIcon,
  Alert,
  Button,
  Group,
  Modal,
  NumberInput,
  Paper,
  Select,
  Stack,
  Table,
  TextInput,
  Title,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { financeApi, type Category, type Transaction, type TransactionFilters } from "./api";
import { MonthlyChart } from "./MonthlyChart";

export function FinancePage() {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<TransactionFilters>({ limit: 50 });
  const [addOpen, setAddOpen] = useState(false);
  const qc = useQueryClient();

  const categories = useQuery({
    queryKey: ["finance", "categories"],
    queryFn: () => financeApi.listCategories(),
  });
  const transactions = useQuery({
    queryKey: ["finance", "transactions", filters],
    queryFn: () => financeApi.listTransactions(filters),
  });
  const totals = useQuery({
    queryKey: ["finance", "monthly-totals"],
    queryFn: () => financeApi.monthlyTotals(),
  });

  const categoriesById = useMemo(() => {
    const m: Record<string, Category> = {};
    (categories.data ?? []).forEach((c) => (m[c.id] = c));
    return m;
  }, [categories.data]);

  const del = useMutation({
    mutationFn: (id: string) => financeApi.deleteTransaction(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["finance"] }),
  });

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>{t("nav.finance")}</Title>
        <Button leftSection={<IconPlus size={16} />} onClick={() => setAddOpen(true)}>
          Add transaction
        </Button>
      </Group>

      {categories.isError && <Alert color="red">{t("common.noAccess")}</Alert>}

      <MonthlyChart totals={totals.data ?? []} />

      <Paper withBorder p="md">
        <Group gap="xs" wrap="wrap" mb="sm">
          <TextInput
            placeholder="Search name / notes"
            value={filters.q ?? ""}
            onChange={(e) => setFilters({ ...filters, q: e.currentTarget.value, offset: 0 })}
            w={240}
          />
          <DatePickerInput
            placeholder="From"
            value={filters.date_from ? new Date(filters.date_from) : null}
            onChange={(d) =>
              setFilters({ ...filters, date_from: d ? d.toISOString().slice(0, 10) : undefined })
            }
            clearable
            w={160}
          />
          <DatePickerInput
            placeholder="To"
            value={filters.date_to ? new Date(filters.date_to) : null}
            onChange={(d) =>
              setFilters({ ...filters, date_to: d ? d.toISOString().slice(0, 10) : undefined })
            }
            clearable
            w={160}
          />
          <NumberInput
            placeholder="Min"
            value={filters.amount_min ? Number(filters.amount_min) : undefined}
            onChange={(v) => setFilters({ ...filters, amount_min: v ? String(v) : undefined })}
            w={120}
            min={0}
          />
          <NumberInput
            placeholder="Max"
            value={filters.amount_max ? Number(filters.amount_max) : undefined}
            onChange={(v) => setFilters({ ...filters, amount_max: v ? String(v) : undefined })}
            w={120}
            min={0}
          />
          <Select
            placeholder="Kind"
            data={[
              { value: "expense", label: "Expense" },
              { value: "income", label: "Income" },
              { value: "transfer", label: "Transfer" },
            ]}
            value={filters.kind ?? null}
            onChange={(v) => setFilters({ ...filters, kind: (v as TransactionFilters["kind"]) ?? undefined })}
            clearable
            w={140}
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
            {(transactions.data ?? []).map((tx: Transaction) => {
              const cat = categoriesById[tx.category_id];
              return (
                <Table.Tr key={tx.id}>
                  <Table.Td>{tx.date}</Table.Td>
                  <Table.Td>{tx.name}</Table.Td>
                  <Table.Td>{cat?.name ?? tx.category_id.slice(0, 8)}</Table.Td>
                  <Table.Td ta="right">
                    {tx.amount} {tx.currency}
                  </Table.Td>
                  <Table.Td>
                    <ActionIcon variant="subtle" color="red" onClick={() => del.mutate(tx.id)}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Paper>

      <AddTransactionModal
        opened={addOpen}
        onClose={() => setAddOpen(false)}
        categories={categories.data ?? []}
      />
    </Stack>
  );
}

function AddTransactionModal(props: {
  opened: boolean;
  onClose: () => void;
  categories: Category[];
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    amount: "0.00",
    currency: "PLN",
    category_id: "",
    person_id: null as string | null,
    name: "",
    notes: "",
  });

  const create = useMutation({
    mutationFn: () => financeApi.createTransaction(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["finance"] });
      props.onClose();
    },
  });

  return (
    <Modal opened={props.opened} onClose={props.onClose} title="Add transaction">
      <Stack>
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
          data={props.categories.map((c) => ({ value: c.id, label: c.name }))}
          value={form.category_id}
          onChange={(v) => setForm({ ...form, category_id: v ?? "" })}
          searchable
          required
        />
        <TextInput
          label="Notes"
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.currentTarget.value })}
        />
        <Button onClick={() => create.mutate()} loading={create.isPending} disabled={!form.category_id || !form.name}>
          Save
        </Button>
      </Stack>
    </Modal>
  );
}
