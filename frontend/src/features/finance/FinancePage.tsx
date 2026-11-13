import { useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Avatar,
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Menu,
  MultiSelect,
  NumberInput,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { DatePickerInput, MonthPickerInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import {
  IconAdjustmentsHorizontal,
  IconBookmarkPlus,
  IconCopy,
  IconDotsVertical,
  IconFileImport,
  IconFilterOff,
  IconPencil,
  IconPlus,
  IconRepeat,
  IconTrash,
} from "@tabler/icons-react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";
import { fmtDate, fmtMonth } from "@/lib/format";

import {
  financeApi,
  type Bookmark,
  type Category,
  type Transaction,
  type TransactionFilters,
} from "./api";
import { categoryOptions, categoryPath } from "./categoryTree";
import { renderCategoryOption } from "./CategoryOption";
import { peopleApi } from "@/features/people/api";

import { BookmarksBar } from "./BookmarksBar";
import { BulkEditModal } from "./BulkEditModal";
import { ImportModal } from "./ImportModal";
import { RecurringModal } from "./RecurringModal";
import { MonthlyChart } from "./MonthlyChart";
import { TransactionModal, type TxModalMode, type TxModalSource } from "./TransactionModal";

/**
 * Finance page — list of transactions with their totals, monthly chart, and
 * add / edit / duplicate controls. Without filters the list shows the month
 * picked at the top (the current one by default); a search (text, amount,
 * category, person) looks through every month, and the date-range filter
 * narrows the list to those days.
 */
export function FinancePage() {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const [month, setMonth] = useState<Date>(() => firstOfMonth(new Date()));
  const [search, setSearch] = useState<Search>(NO_SEARCH);
  // The range being picked, and the one applied (once both days are picked).
  const [picking, setPicking] = useState<[Date | null, Date | null]>([null, null]);
  const [range, setRange] = useState<[Date, Date] | null>(null);
  const searching = !!(
    search.q.trim() ||
    search.amount_min ||
    search.amount_max ||
    search.category_ids.length ||
    search.person_ids.length
  );
  function clearFilters() {
    setSearch(NO_SEARCH);
    setPicking([null, null]);
    setRange(null);
  }
  const [recurringOpen, setRecurringOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  // Rows ticked for "change many" (cleared when the filters change).
  const [ticked, setTicked] = useState<string[]>([]);
  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const peopleById = useMemo(
    () => Object.fromEntries((people.data ?? []).map((p) => [p.id, p])),
    [people.data],
  );

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
    // The picked days; else every month when searching; else the month.
    const period = range
      ? { date_from: iso(range[0]), date_to: iso(range[1]) }
      : searching
        ? {}
        : monthRange(month);
    const category_keys = search.category_ids
      .map((id) => categoriesById[id]?.key)
      .filter((k): k is string => !!k);
    return {
      ...period,
      q: search.q.trim() || undefined,
      amount_min: search.amount_min,
      amount_max: search.amount_max,
      category_keys: category_keys.length ? category_keys : undefined,
      person_ids: search.person_ids.length ? search.person_ids : undefined,
    };
  }, [month, search, searching, range, categoriesById]);
  const scopeLabel = range
    ? `${fmtDate(iso(range[0]))} – ${fmtDate(iso(range[1]))}`
    : searching
      ? t("finance.search.allMonths")
      : fmtMonth(month);

  // The newest PAGE rows; "show older" adds another PAGE (for these filters).
  const filtersKey = JSON.stringify(filters);
  const [older, setOlder] = useState<{ key: string; limit: number } | null>(null);
  const limit = older?.key === filtersKey ? older.limit : PAGE;
  const transactionsQ = useQuery({
    queryKey: ["finance", "transactions", filters, limit],
    queryFn: () => financeApi.listTransactions({ ...filters, limit }),
    placeholderData: keepPreviousData,
  });
  const hasOlder = (transactionsQ.data?.length ?? 0) >= limit;
  useEffect(() => setTicked([]), [filters]);
  const shownIds = (transactionsQ.data ?? []).map((tx) => tx.id);
  const allTicked = shownIds.length > 0 && shownIds.every((id) => ticked.includes(id));
  const toggle = (id: string) => setTicked((l) => (l.includes(id) ? l.filter((x) => x !== id) : [...l, id]));
  // The chart shows the 12 months ending with the picked month, so the month
  // must be part of the query key or the cached window never changes.
  const monthIso = iso(month);
  const totalsQ = useQuery({
    queryKey: ["finance", "monthly-totals", monthIso, CHART_MONTHS],
    queryFn: () => financeApi.monthlyTotals(monthIso, CHART_MONTHS),
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
  function openFromBookmark(b: Bookmark) {
    setModalMode("bookmark");
    // The modal only reads the transaction fields a bookmark also has.
    setModalSource({
      ...b,
      id: "",
      date: "",
      recurring_rule_id: null,
      source_id: null,
      related_kind: "",
      related_id: null,
    });
    setModalOpen(true);
  }

  const saveBookmark = useMutation({
    mutationFn: (tx: Transaction) =>
      financeApi.createBookmark({
        label: tx.name.slice(0, 60),
        name: tx.name,
        amount: tx.amount,
        currency: tx.currency,
        category_id: tx.category_id,
        person_id: tx.person_id,
        notes: tx.notes,
        shares: tx.shares,
      }),
    onSuccess: (b) => {
      qc.invalidateQueries({ queryKey: ["finance", "bookmarks"] });
      notifications.show({ message: t("finance.bookmarks.saved", { label: b.label }) });
    },
  });

  return (
    <Stack gap="lg">
      <PageHeader
        title={t("nav.transactions")}
        subtitle={t("page.transactions.subtitle")}
        actions={
        <>
          <MonthPickerInput
            value={month}
            onChange={(d) => d && setMonth(firstOfMonth(d))}
            valueFormat="MMMM YYYY"
            w={200}
          />
          <Button variant="light" leftSection={<IconFileImport size={16} />} onClick={() => setImportOpen(true)}>
            {t("finance.import.button")}
          </Button>
          <Button variant="light" leftSection={<IconRepeat size={16} />} onClick={() => setRecurringOpen(true)}>
            {t("finance.recurring.title")}
          </Button>
          <Button leftSection={<IconPlus size={16} />} onClick={openNew}>
            {t("finance.tx.add")}
          </Button>
        </>
        }
      />

      {categoriesQ.isError && <Alert color="red">{t("common.noAccess")}</Alert>}

      <MonthlyChart totals={totalsQ.data ?? []} endMonth={month} months={CHART_MONTHS} />

      <Paper withBorder p="md">
        <BookmarksBar onPick={openFromBookmark} />
      </Paper>

      <Paper withBorder p="md">
        <Group gap="xs" wrap="wrap" mb="sm">
          <TextInput
            placeholder={t("finance.search.text")}
            value={search.q}
            onChange={(e) => setSearch({ ...search, q: e.currentTarget.value })}
            w={240}
          />
          <DatePickerInput
            type="range"
            allowSingleDateInRange
            clearable
            valueFormat="DD.MM.YYYY"
            placeholder={t("finance.search.dates")}
            aria-label={t("finance.search.dates")}
            value={picking}
            onChange={(v) => {
              setPicking(v);
              if (v[0] && v[1]) setRange([v[0], v[1]]);
              else if (!v[0] && !v[1]) setRange(null);
            }}
            w={230}
          />
          <NumberInput
            placeholder={t("finance.search.min")}
            value={search.amount_min ? Number(search.amount_min) : ""}
            onChange={(v) => setSearch({ ...search, amount_min: v ? String(v) : undefined })}
            w={120}
            min={0}
          />
          <NumberInput
            placeholder={t("finance.search.max")}
            value={search.amount_max ? Number(search.amount_max) : ""}
            onChange={(v) => setSearch({ ...search, amount_max: v ? String(v) : undefined })}
            w={120}
            min={0}
          />
          <MultiSelect
            placeholder={t("finance.search.category")}
            // A main category also finds its sub-categories' transactions.
            data={(["expense", "income"] as const).map((kind) => ({
              group: t(`finance.chart.${kind}`),
              items: categoryOptions((categoriesQ.data ?? []).filter((c) => c.kind === kind)),
            }))}
            renderOption={renderCategoryOption}
            value={search.category_ids}
            onChange={(ids) => setSearch({ ...search, category_ids: ids })}
            searchable
            clearable
            w={320}
          />
          <MultiSelect
            placeholder={t("finance.search.forWhom")}
            data={(people.data ?? []).map((p) => ({ value: p.id, label: p.display_name }))}
            value={search.person_ids}
            onChange={(ids) => setSearch({ ...search, person_ids: ids })}
            clearable
            w={220}
          />
          {(searching || range) && (
            <Button variant="subtle" color="gray" leftSection={<IconFilterOff size={16} />} onClick={clearFilters}>
              {t("finance.search.clear")}
            </Button>
          )}
          <Button
            variant="light"
            leftSection={<IconAdjustmentsHorizontal size={16} />}
            onClick={() => setBulkOpen(true)}
            ml="auto"
          >
            {ticked.length ? t("finance.bulk.buttonTicked", { count: ticked.length }) : t("finance.bulk.button")}
          </Button>
        </Group>

        {/* What the list holds, and its totals. */}
        <Group gap="xs" mb="sm">
          <Text fw={600}>
            {scopeLabel}
          </Text>
          <Badge color="teal" variant="light">
            {t("finance.totals.income", { value: monthTotals.income.toFixed(2) })}
          </Badge>
          <Badge color="red" variant="light">
            {t("finance.totals.expense", { value: monthTotals.expense.toFixed(2) })}
          </Badge>
          <Badge color="gray" variant="light">
            {t("finance.totals.net", {
              value: (monthTotals.income - monthTotals.expense).toFixed(2),
            })}
          </Badge>
          {hasOlder && (
            <Text size="xs" c="dimmed">
              {t("finance.totals.partial", { count: limit })}
            </Text>
          )}
        </Group>

        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={36}>
                <Checkbox
                  size="xs"
                  aria-label={t("finance.bulk.tickAll")}
                  checked={allTicked}
                  indeterminate={ticked.length > 0 && !allTicked}
                  onChange={() => setTicked(allTicked ? [] : shownIds)}
                />
              </Table.Th>
              {/* Phones: date, category and who under the name. */}
              <Table.Th visibleFrom="sm">{t("finance.field.date")}</Table.Th>
              <Table.Th>{t("finance.field.name")}</Table.Th>
              <Table.Th visibleFrom="sm">{t("finance.field.category")}</Table.Th>
              <Table.Th visibleFrom="sm">{t("finance.field.forWhom")}</Table.Th>
              <Table.Th ta="right">{t("finance.field.amount")}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(transactionsQ.data ?? []).map((tx: Transaction) => {
              const cat = categoriesById[tx.category_id];
              return (
                <Table.Tr key={tx.id} bg={ticked.includes(tx.id) ? "var(--mantine-primary-color-light)" : undefined}>
                  <Table.Td>
                    <Checkbox size="xs" aria-label={tx.name} checked={ticked.includes(tx.id)} onChange={() => toggle(tx.id)} />
                  </Table.Td>
                  <Table.Td visibleFrom="sm" style={{ whiteSpace: "nowrap" }}>
                    {tx.date}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      {tx.recurring_rule_id && (
                        <Tooltip label={t("finance.recurring.badge")}>
                          <IconRepeat size={14} color="var(--mantine-color-dimmed)" />
                        </Tooltip>
                      )}
                      {tx.name}
                    </Group>
                    <Text size="xs" c="dimmed" hiddenFrom="sm">
                      {[
                        fmtDate(tx.date),
                        cat ? categoryPath(cat, categoriesById) : null,
                        tx.shares.length
                          ? tx.shares.map((s) => peopleById[s.person_id]?.display_name ?? "…").join(", ")
                          : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </Text>
                  </Table.Td>
                  <Table.Td visibleFrom="sm">{cat ? categoryPath(cat, categoriesById) : tx.category_id.slice(0, 8)}</Table.Td>
                  <Table.Td visibleFrom="sm">
                    {tx.shares.length ? (
                      <Avatar.Group spacing={6}>
                        {tx.shares.map((s) => {
                          const p = peopleById[s.person_id];
                          return (
                            <Tooltip
                              key={s.person_id}
                              label={`${p?.display_name ?? "…"}${tx.shares.length > 1 ? ` · ${s.amount} ${tx.currency}` : ""}`}
                            >
                              <Avatar size="sm" radius="xl" color={p?.color} variant="filled">
                                {(p?.display_name ?? "?").slice(0, 2).toUpperCase()}
                              </Avatar>
                            </Tooltip>
                          );
                        })}
                      </Avatar.Group>
                    ) : (
                      <Text size="xs" c="dimmed">
                        {t("finance.field.forWhomShared")}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td ta="right" c={cat?.kind === "income" ? "teal" : undefined} style={{ whiteSpace: "nowrap" }}>
                    {tx.amount} {tx.currency}
                  </Table.Td>
                  <Table.Td>
                    {/* Phones: one menu instead of four buttons. */}
                    <Menu position="bottom-end" withinPortal>
                      <Menu.Target>
                        <ActionIcon variant="subtle" color="gray" hiddenFrom="sm" aria-label={t("finance.action.more")}>
                          <IconDotsVertical size={16} />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item leftSection={<IconPencil size={14} />} onClick={() => openEdit(tx)}>
                          {t("finance.action.edit")}
                        </Menu.Item>
                        <Menu.Item leftSection={<IconCopy size={14} />} onClick={() => openDuplicate(tx)}>
                          {t("finance.action.duplicate")}
                        </Menu.Item>
                        <Menu.Item leftSection={<IconBookmarkPlus size={14} />} onClick={() => saveBookmark.mutate(tx)}>
                          {t("finance.bookmarks.add")}
                        </Menu.Item>
                        <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() => del.mutate(tx.id)}>
                          {t("finance.action.delete")}
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                    <Group gap={4} justify="flex-end" wrap="nowrap" visibleFrom="sm">
                      <Tooltip label={t("finance.action.edit")}>
                        <ActionIcon variant="subtle" onClick={() => openEdit(tx)}>
                          <IconPencil size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label={t("finance.action.duplicate")}>
                        <ActionIcon variant="subtle" onClick={() => openDuplicate(tx)}>
                          <IconCopy size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label={t("finance.bookmarks.add")}>
                        <ActionIcon variant="subtle" onClick={() => saveBookmark.mutate(tx)}>
                          <IconBookmarkPlus size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label={t("finance.action.delete")}>
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
                <Table.Td colSpan={7} ta="center" c="dimmed" py="md">
                  {searching || range ? t("finance.tx.noMatch") : t("finance.tx.empty")}
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
        {hasOlder && (
          <Group justify="center" mt="sm">
            <Button
              variant="subtle"
              loading={transactionsQ.isFetching}
              onClick={() => setOlder({ key: filtersKey, limit: limit + PAGE })}
            >
              {t("finance.tx.older")}
            </Button>
          </Group>
        )}
      </Paper>

      <BulkEditModal
        opened={bulkOpen}
        onClose={() => setBulkOpen(false)}
        filters={filters}
        scope={scopeLabel}
        ids={ticked}
        categories={categoriesQ.data ?? []}
        people={people.data ?? []}
        onDone={() => setTicked([])}
      />
      <ImportModal
        opened={importOpen}
        onClose={() => setImportOpen(false)}
        categories={categoriesQ.data ?? []}
        people={people.data ?? []}
      />
      <RecurringModal
        opened={recurringOpen}
        onClose={() => setRecurringOpen(false)}
        categoriesById={categoriesById}
        peopleById={peopleById}
      />
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

const CHART_MONTHS = 12;
const PAGE = 500; // rows per "show older"

type Search = {
  q: string;
  amount_min: string | undefined;
  amount_max: string | undefined;
  category_ids: string[];
  person_ids: string[];
};
const NO_SEARCH: Search = { q: "", amount_min: undefined, amount_max: undefined, category_ids: [], person_ids: [] };

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
