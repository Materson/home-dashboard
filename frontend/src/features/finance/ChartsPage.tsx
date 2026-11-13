/**
 * Finanse → Wykresy, for the chosen period: income vs expenses month by
 * month (or lines to compare — per category, person or search word), and
 * expenses / income per category and expenses per person (pies — many
 * categories are folded into "Pozostałe", the full list sits next to each
 * pie). The category pies show main categories — or, with categories
 * picked in the filter, those (a picked sub-category is its own slice);
 * clicking one with sub-categories in the list opens its split. The filters (words, amount,
 * categories, people) apply to every chart; "Dla kogo" counts only those
 * people's parts of split transactions, and "Wspólne" the household's
 * unsplit spending. The pies cover the picked period — one month in the
 * month mode, while the line spans 12 — so each says its period and which
 * picked categories have nothing in it. Dragging across the line picks
 * those months as the period.
 */
import { type ReactNode, useMemo, useState } from "react";
import { DonutChart, LineChart } from "@mantine/charts";
import {
  Button,
  Grid,
  Group,
  MultiSelect,
  NumberInput,
  Paper,
  ScrollArea,
  SegmentedControl,
  Stack,
  Table,
  TagsInput,
  Text,
  Title,
} from "@mantine/core";
import { DatePickerInput, MonthPickerInput, YearPickerInput } from "@mantine/dates";
import { IconArrowLeft, IconChevronRight, IconFilterOff } from "@tabler/icons-react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";
import { useRangeSelect } from "@/components/useRangeSelect";

import { peopleApi } from "@/features/people/api";
import { fmtDate, fmtMoney, fmtMonth } from "@/lib/format";

import { type ChartFilters, financeApi, type LineSplit, type Slice } from "./api";
import { categoryOptions, categoryPath, indexById } from "./categoryTree";
import { renderCategoryOption } from "./CategoryOption";
import {
  compareLines,
  distinctColors,
  monthKeys,
  monthlyLine,
  monthSpan,
  type PeriodMode,
  periodRange,
  type PieSlice,
  topSlices,
} from "./chartData";

type OpenGroup = { id: string; name: string } | null;
type LineMode = "kind" | LineSplit;
type Filters = {
  q: string[];
  amount_min?: string;
  amount_max?: string;
  category_ids: string[];
  persons: string[]; // people's ids and/or "shared"
};
const NO_FILTERS: Filters = { q: [], category_ids: [], persons: [] };

const KEEP = 8; // slices shown before "Pozostałe"; lines compared at once

export function ChartsPage() {
  const { t } = useTranslation();
  const [mode, setMode] = useState<PeriodMode>("month");
  const [ref, setRef] = useState<Date>(() => new Date());
  // Custom range: the last complete pick is used (a half-picked range is ignored).
  const [picking, setPicking] = useState<[Date | null, Date | null]>(() => {
    const now = new Date();
    return [new Date(now.getFullYear(), now.getMonth() - 2, 1), now];
  });
  const [range, setRange] = useState<[Date, Date]>(() => picking as [Date, Date]);
  const { from, to, endMonth, months } = periodRange(mode, ref, range);
  const until = `${endMonth.getFullYear()}-${String(endMonth.getMonth() + 1).padStart(2, "0")}-01`;
  // What the pies cover (the line always spans `months`).
  const period =
    mode === "month"
      ? fmtMonth(ref)
      : mode === "year"
        ? String(ref.getFullYear())
        : `${fmtDate(from)} – ${fmtDate(to)}`;

  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const filtered = !!(
    filters.q.length ||
    filters.amount_min ||
    filters.amount_max ||
    filters.category_ids.length ||
    filters.persons.length
  );
  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const categories = useQuery({ queryKey: ["finance", "categories"], queryFn: () => financeApi.listCategories() });
  const categoriesById = useMemo(() => indexById(categories.data ?? []), [categories.data]);
  const withSubs = new Set((categories.data ?? []).flatMap((c) => (c.parent_id ? [c.parent_id] : [])));
  const f: ChartFilters = useMemo(() => {
    const keys = filters.category_ids.map((id) => categoriesById[id]?.key).filter((k): k is string => !!k);
    return {
      q: filters.q.length ? filters.q : undefined,
      amount_min: filters.amount_min,
      amount_max: filters.amount_max,
      category_keys: keys.length ? keys : undefined,
      persons: filters.persons.length ? filters.persons : undefined,
    };
  }, [filters, categoriesById]);

  // The line: income vs expenses, or lines to compare.
  const [lineMode, setLineMode] = useState<LineMode>("kind");
  const noWords = lineMode === "term" && !filters.q.length;
  const line = useQuery({
    queryKey: ["finance", "charts", "line", until, months, f],
    queryFn: () => financeApi.monthlyTotals(until, months, f),
    enabled: lineMode === "kind",
    placeholderData: keepPreviousData,
  });
  const series = useQuery({
    queryKey: ["finance", "charts", "series", lineMode, until, months, f],
    queryFn: () => financeApi.monthlySeries(lineMode as LineSplit, until, months, f),
    enabled: lineMode !== "kind" && !noWords,
    // Keep the lines while new filters load — not across modes (other keys).
    placeholderData: (prev, prevQuery) => (prevQuery?.queryKey[3] === lineMode ? prev : undefined),
  });

  // A main category opened in a pie (its sub-categories), per pie.
  const [expenseGroup, setExpenseGroup] = useState<OpenGroup>(null);
  const [incomeGroup, setIncomeGroup] = useState<OpenGroup>(null);
  const expenses = useQuery({
    queryKey: ["finance", "charts", "cat", "expense", from, to, f, expenseGroup?.id],
    queryFn: () => financeApi.categoryTotals(from, to, "expense", f, expenseGroup?.id),
    placeholderData: keepPreviousData,
  });
  const income = useQuery({
    queryKey: ["finance", "charts", "cat", "income", from, to, f, incomeGroup?.id],
    queryFn: () => financeApi.categoryTotals(from, to, "income", f, incomeGroup?.id),
    placeholderData: keepPreviousData,
  });
  // One person picked: their pie would be a single slice.
  const showPeople = filters.persons.length !== 1;
  const byPerson = useQuery({
    queryKey: ["finance", "charts", "people", from, to, f],
    queryFn: () => financeApi.personTotals(from, to, "expense", f),
    enabled: showPeople,
    placeholderData: keepPreviousData,
  });

  const other = t("finance.charts.other");
  const shared = t("finance.field.forWhomShared");
  const peopleById = useMemo(() => Object.fromEntries((people.data ?? []).map((p) => [p.id, p])), [people.data]);
  const describe = (key: string): { label: string; color: string } => {
    if (lineMode === "category") {
      const cat = categoriesById[key];
      return cat ? { label: categoryPath(cat, categoriesById), color: cat.color } : { label: "…", color: "" };
    }
    if (lineMode === "person") {
      if (key === "shared") return { label: shared, color: "" };
      const p = peopleById[key];
      return { label: p?.display_name ?? "…", color: p?.color ?? "" };
    }
    return { label: key, color: "" };
  };
  const compared =
    lineMode === "kind"
      ? null
      : compareLines(series.data ?? [], endMonth, months, describe, {
          expense: t("finance.chart.expense"),
          income: t("finance.chart.income"),
        }, KEEP);
  const money = (v: number) => fmtMoney(v.toFixed(2), "PLN");
  // Dragging across the line picks those months as the period (every chart).
  const drag = useRangeSelect(monthKeys(endMonth, months), (i, j) => {
    const span = monthSpan(endMonth, months, i, j);
    setPicking(span);
    setRange(span);
    setMode("range");
  });

  return (
    <Stack gap="lg">
      <PageHeader
        title={t("finance.charts.title")}
        subtitle={t("page.charts.subtitle")}
        actions={
        <>
          <SegmentedControl
            value={mode}
            onChange={(v) => setMode(v as PeriodMode)}
            data={[
              { value: "month", label: t("finance.charts.month") },
              { value: "year", label: t("finance.charts.year") },
              { value: "last12", label: t("finance.charts.last12") },
              { value: "range", label: t("finance.charts.range") },
            ]}
          />
          {mode === "range" ? (
            <DatePickerInput
              type="range"
              allowSingleDateInRange
              value={picking}
              onChange={(v) => {
                setPicking(v);
                if (v[0] && v[1]) setRange([v[0], v[1]]);
              }}
              valueFormat="DD.MM.YYYY"
              w={240}
              aria-label={t("finance.charts.range")}
            />
          ) : mode === "year" ? (
            <YearPickerInput value={ref} onChange={(d) => d && setRef(d)} w={110} />
          ) : (
            <MonthPickerInput value={ref} onChange={(d) => d && setRef(d)} valueFormat="MMMM YYYY" w={180} />
          )}
        </>
        }
      />

      <Paper withBorder p="md">
        <Group gap="xs" wrap="wrap">
          <TagsInput
            placeholder={filters.q.length ? undefined : t("finance.charts.words")}
            aria-label={t("finance.charts.words")}
            value={filters.q}
            onChange={(q) => setFilters({ ...filters, q })}
            splitChars={[","]}
            clearable
            w={260}
          />
          <NumberInput
            placeholder={t("finance.search.min")}
            value={filters.amount_min ? Number(filters.amount_min) : ""}
            onChange={(v) => setFilters({ ...filters, amount_min: v ? String(v) : undefined })}
            w={110}
            min={0}
          />
          <NumberInput
            placeholder={t("finance.search.max")}
            value={filters.amount_max ? Number(filters.amount_max) : ""}
            onChange={(v) => setFilters({ ...filters, amount_max: v ? String(v) : undefined })}
            w={110}
            min={0}
          />
          <MultiSelect
            placeholder={t("finance.search.category")}
            // A main category also brings its sub-categories.
            data={(["expense", "income"] as const).map((kind) => ({
              group: t(`finance.chart.${kind}`),
              items: categoryOptions((categories.data ?? []).filter((c) => c.kind === kind)),
            }))}
            renderOption={renderCategoryOption}
            value={filters.category_ids}
            onChange={(category_ids) => setFilters({ ...filters, category_ids })}
            searchable
            clearable
            w={300}
          />
          <MultiSelect
            placeholder={t("finance.search.forWhom")}
            data={[
              ...(people.data ?? []).map((p) => ({ value: p.id, label: p.display_name })),
              { value: "shared", label: shared },
            ]}
            value={filters.persons}
            onChange={(persons) => setFilters({ ...filters, persons })}
            clearable
            w={240}
          />
          {filtered && (
            <Button variant="subtle" color="gray" leftSection={<IconFilterOff size={16} />} onClick={() => setFilters(NO_FILTERS)}>
              {t("finance.search.clear")}
            </Button>
          )}
        </Group>
        <Text size="xs" c="dimmed" mt={6}>
          {t("finance.charts.filtersHint")}
        </Text>
      </Paper>

      <Paper withBorder p="md">
        <Group justify="space-between" mb="sm" gap="xs">
          <Title order={5}>
            {lineMode === "kind"
              ? t("finance.charts.trend", { count: months })
              : t("finance.charts.compare", { count: months })}
          </Title>
          <SegmentedControl
            size="xs"
            value={lineMode}
            onChange={(v) => setLineMode(v as LineMode)}
            data={[
              { value: "kind", label: t("finance.charts.lines.kind") },
              { value: "category", label: t("finance.charts.lines.category") },
              { value: "person", label: t("finance.charts.lines.person") },
              { value: "term", label: t("finance.charts.lines.term") },
            ]}
          />
        </Group>
        {lineMode === "kind" ? (
          <LineChart
            h={260}
            data={monthlyLine(line.data ?? [], endMonth, months)}
            dataKey="month"
            {...drag.chartProps}
            withLegend
            curveType="monotone"
            valueFormatter={money}
            series={[
              { name: "income", label: t("finance.chart.income"), color: "teal.6" },
              { name: "expense", label: t("finance.chart.expense"), color: "red.6" },
              { name: "balance", label: t("finance.charts.balance"), color: "gray.5", strokeDasharray: "5 5" },
            ]}
          >
            {drag.area}
          </LineChart>
        ) : noWords ? (
          <Text size="sm" c="dimmed" py="xl" ta="center">
            {t("finance.charts.lines.noWords")}
          </Text>
        ) : compared && !compared.lines.length && !series.isFetching ? (
          <Text size="sm" c="dimmed" py="xl" ta="center">
            {t("finance.charts.noData")}
          </Text>
        ) : (
          <LineChart
            h={260}
            data={compared?.data ?? []}
            dataKey="month"
            {...drag.chartProps}
            withLegend
            curveType="monotone"
            valueFormatter={money}
            series={compared?.lines ?? []}
          >
            {drag.area}
          </LineChart>
        )}
        <Text size="xs" c="dimmed" mt="xs">
          {[
            lineMode !== "kind" && t(`finance.charts.lines.${lineMode}Hint`),
            compared?.hidden && t("finance.charts.lines.hidden", { count: compared.hidden }),
            t("finance.charts.dragHint"),
          ]
            .filter(Boolean)
            .join(" ")}
        </Text>
      </Paper>

      <Grid>
        {(
          [
            ["expense", "finance.charts.expensesByCategory", expenses.data, expenseGroup, setExpenseGroup],
            ["income", "finance.charts.incomeByCategory", income.data, incomeGroup, setIncomeGroup],
          ] as const
        ).map(([kind, title, data, group, setGroup]) => {
          // Picked categories of this kind with nothing in the period.
          const shown = new Set((data ?? []).map((s) => s.key));
          const missing = group
            ? []
            : filters.category_ids.filter((id) => categoriesById[id]?.kind === kind && !shown.has(id));
          const full = distinctColors(
            // What was booked straight into the opened main category, named so.
            // A picked sub-category (its own slice) shows its main one too.
            (data ?? []).map((s) =>
              group && s.key === group.id
                ? { ...s, label: t("finance.charts.groupItself", { name: group.name }) }
                : !group && categoriesById[s.key]?.parent_id
                  ? { ...s, label: categoryPath(categoriesById[s.key], categoriesById) }
                  : s,
            ),
          );
          return (
            <Grid.Col key={title} span={{ base: 12, lg: showPeople ? 4 : 6 }}>
              <PieCard
                title={group ? t("finance.charts.inGroup", { title: t(title), name: group.name }) : t(title)}
                period={period}
                note={
                  // Only once loaded — not while the new filters are on their way.
                  data && !(kind === "expense" ? expenses : income).isPlaceholderData && missing.length ? (
                    <>
                      {t("finance.charts.missing", {
                        names: missing.map((id) => categoryPath(categoriesById[id], categoriesById)).join(", "),
                      })}
                      {mode === "month" && (
                        <Button size="compact-xs" variant="subtle" ml={4} onClick={() => setMode("last12")}>
                          {t("finance.charts.showLast12")}
                        </Button>
                      )}
                    </>
                  ) : null
                }
                // Every picked category gets its slice, not "Pozostałe".
                slices={topSlices(full, Math.max(KEEP, filters.category_ids.length), other)}
                full={full}
                canOpen={(key) => !group && withSubs.has(key)}
                onOpen={(slice) => setGroup({ id: slice.key, name: slice.label })}
                onBack={group ? () => setGroup(null) : undefined}
              />
            </Grid.Col>
          );
        })}
        {showPeople && (
          <Grid.Col span={{ base: 12, lg: 4 }}>
            <PieCard
              title={t("finance.charts.expensesByPerson")}
              period={period}
              slices={topSlices(distinctColors(byPerson.data ?? []), KEEP, other, shared)}
              full={distinctColors(byPerson.data ?? [])}
              sharedLabel={shared}
            />
          </Grid.Col>
        )}
      </Grid>
    </Stack>
  );
}

function PieCard(props: {
  title: string;
  /** The period it covers, under the title. */
  period: string;
  /** E.g. which picked categories have nothing in the period. */
  note?: ReactNode;
  slices: PieSlice[];
  full: Slice[];
  sharedLabel?: string;
  /** A main category with sub-categories: its row opens them. */
  canOpen?: (key: string) => boolean;
  onOpen?: (slice: Slice) => void;
  onBack?: () => void;
}) {
  const { t } = useTranslation();
  const total = props.full.reduce((n, s) => n + Number(s.total), 0);
  return (
    <Paper withBorder p="md" h="100%">
      <Group justify="space-between" mb="sm" wrap="nowrap" align="flex-start">
        <div>
          <Title order={5}>{props.title}</Title>
          <Text size="xs" c="dimmed">
            {props.period}
          </Text>
        </div>
        {props.onBack && (
          <Button size="compact-xs" variant="subtle" leftSection={<IconArrowLeft size={14} />} onClick={props.onBack}>
            {t("finance.charts.allCategories")}
          </Button>
        )}
      </Group>
      {props.note && (
        <Text size="xs" c="dimmed" mb="sm">
          {props.note}
        </Text>
      )}
      {!props.full.length ? (
        !props.note && (
          <Text size="sm" c="dimmed">
            {t("finance.charts.noData")}
          </Text>
        )
      ) : (
        <Stack gap="sm" align="center">
          <DonutChart
            data={props.slices.map(({ name, value, color }) => ({ name, value, color }))}
            size={180}
            thickness={28}
            withTooltip
            tooltipDataSource="segment"
            valueFormatter={(v) => fmtMoney(v.toFixed(2), "PLN")}
            chartLabel={fmtMoney(total.toFixed(2), "PLN")}
          />
          <ScrollArea.Autosize mah={220} w="100%">
            <Table verticalSpacing={2} fz="sm">
              <Table.Tbody>
                {props.full.map((s) => {
                  const opens = !!props.onOpen && !!props.canOpen?.(s.key);
                  return (
                  <Table.Tr
                    key={s.key}
                    onClick={opens ? () => props.onOpen?.(s) : undefined}
                    style={opens ? { cursor: "pointer" } : undefined}
                    title={opens ? t("finance.charts.openGroup") : undefined}
                  >
                    <Table.Td>
                      <Group gap={6} wrap="nowrap">
                        <div style={{ width: 10, height: 10, borderRadius: 2, background: s.color, flexShrink: 0 }} />
                        <Text size="sm" truncate>
                          {s.key === "shared" ? props.sharedLabel : s.label}
                        </Text>
                        {opens && <IconChevronRight size={14} color="var(--mantine-color-dimmed)" style={{ flexShrink: 0 }} />}
                      </Group>
                    </Table.Td>
                    <Table.Td ta="right">{fmtMoney(s.total, "PLN")}</Table.Td>
                    <Table.Td ta="right" c="dimmed" w={50}>
                      {total ? Math.round((Number(s.total) / total) * 100) : 0}%
                    </Table.Td>
                  </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea.Autosize>
        </Stack>
      )}
    </Paper>
  );
}
