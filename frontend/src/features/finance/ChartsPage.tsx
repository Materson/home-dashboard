/**
 * Finanse → Wykresy: income vs expenses over 12 months (line), and for the
 * chosen period expenses / income per category and expenses per person
 * (pies — many categories are folded into "Pozostałe", the full list sits
 * next to each pie). The category pies show main categories; clicking one
 * with sub-categories in the list opens its split. "Dla kogo" narrows
 * everything to one person's parts of split transactions, or to the
 * household's unsplit spending.
 */
import { useState } from "react";
import { DonutChart, LineChart } from "@mantine/charts";
import {
  Button,
  Grid,
  Group,
  Paper,
  ScrollArea,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { DatePickerInput, MonthPickerInput, YearPickerInput } from "@mantine/dates";
import { IconArrowLeft, IconChevronRight } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";

import { peopleApi } from "@/features/people/api";
import { fmtMoney } from "@/lib/format";

import { financeApi, type Slice } from "./api";
import { distinctColors, monthlyLine, type PeriodMode, periodRange, type PieSlice, topSlices } from "./chartData";

type OpenGroup = { id: string; name: string } | null;

const KEEP = 8; // slices shown before "Pozostałe"

export function ChartsPage() {
  const { t } = useTranslation();
  const [mode, setMode] = useState<PeriodMode>("month");
  const [ref, setRef] = useState<Date>(() => new Date());
  const [person, setPerson] = useState<string | null>(null);
  // Custom range: the last complete pick is used (a half-picked range is ignored).
  const [picking, setPicking] = useState<[Date | null, Date | null]>(() => {
    const now = new Date();
    return [new Date(now.getFullYear(), now.getMonth() - 2, 1), now];
  });
  const [range, setRange] = useState<[Date, Date]>(() => picking as [Date, Date]);
  const { from, to, endMonth, months } = periodRange(mode, ref, range);
  const until = `${endMonth.getFullYear()}-${String(endMonth.getMonth() + 1).padStart(2, "0")}-01`;

  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const line = useQuery({
    queryKey: ["finance", "charts", "line", until, months, person],
    queryFn: () => financeApi.monthlyTotals(until, months, person),
  });
  // A main category opened in a pie (its sub-categories), per pie.
  const [expenseGroup, setExpenseGroup] = useState<OpenGroup>(null);
  const [incomeGroup, setIncomeGroup] = useState<OpenGroup>(null);
  const categories = useQuery({ queryKey: ["finance", "categories"], queryFn: () => financeApi.listCategories() });
  const withSubs = new Set((categories.data ?? []).flatMap((c) => (c.parent_id ? [c.parent_id] : [])));
  const expenses = useQuery({
    queryKey: ["finance", "charts", "cat", "expense", from, to, person, expenseGroup?.id],
    queryFn: () => financeApi.categoryTotals(from, to, "expense", person, expenseGroup?.id),
  });
  const income = useQuery({
    queryKey: ["finance", "charts", "cat", "income", from, to, person, incomeGroup?.id],
    queryFn: () => financeApi.categoryTotals(from, to, "income", person, incomeGroup?.id),
  });
  const byPerson = useQuery({
    queryKey: ["finance", "charts", "people", from, to],
    queryFn: () => financeApi.personTotals(from, to, "expense"),
    enabled: !person,
  });

  const other = t("finance.charts.other");
  const shared = t("finance.field.forWhomShared");
  const personOptions = [
    { value: "", label: t("finance.charts.everyone") },
    ...(people.data ?? []).map((p) => ({ value: p.id, label: p.display_name })),
    { value: "shared", label: shared },
  ];

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
          <Select
            data={personOptions}
            value={person ?? ""}
            onChange={(v) => setPerson(v || null)}
            allowDeselect={false}
            w={200}
            aria-label={t("finance.field.forWhom")}
          />
        </>
        }
      />

      <Paper withBorder p="md">
        <Title order={5} mb="sm">
          {t("finance.charts.trend", { count: months })}
        </Title>
        <LineChart
          h={260}
          data={monthlyLine(line.data ?? [], endMonth, months)}
          dataKey="month"
          withLegend
          curveType="monotone"
          valueFormatter={(v) => fmtMoney(v.toFixed(2), "PLN")}
          series={[
            { name: "income", label: t("finance.chart.income"), color: "teal.6" },
            { name: "expense", label: t("finance.chart.expense"), color: "red.6" },
            { name: "balance", label: t("finance.charts.balance"), color: "gray.5", strokeDasharray: "5 5" },
          ]}
        />
      </Paper>

      <Grid>
        {(
          [
            ["finance.charts.expensesByCategory", expenses.data, expenseGroup, setExpenseGroup],
            ["finance.charts.incomeByCategory", income.data, incomeGroup, setIncomeGroup],
          ] as const
        ).map(([title, data, group, setGroup]) => {
          const full = distinctColors(
            // What was booked straight into the opened main category, named so.
            (data ?? []).map((s) =>
              group && s.key === group.id ? { ...s, label: t("finance.charts.groupItself", { name: group.name }) } : s,
            ),
          );
          return (
            <Grid.Col key={title} span={{ base: 12, lg: person ? 6 : 4 }}>
              <PieCard
                title={group ? t("finance.charts.inGroup", { title: t(title), name: group.name }) : t(title)}
                slices={topSlices(full, KEEP, other)}
                full={full}
                canOpen={(key) => !group && withSubs.has(key)}
                onOpen={(slice) => setGroup({ id: slice.key, name: slice.label })}
                onBack={group ? () => setGroup(null) : undefined}
              />
            </Grid.Col>
          );
        })}
        {!person && (
          <Grid.Col span={{ base: 12, lg: 4 }}>
            <PieCard
              title={t("finance.charts.expensesByPerson")}
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
      <Group justify="space-between" mb="sm" wrap="nowrap">
        <Title order={5}>{props.title}</Title>
        {props.onBack && (
          <Button size="compact-xs" variant="subtle" leftSection={<IconArrowLeft size={14} />} onClick={props.onBack}>
            {t("finance.charts.allCategories")}
          </Button>
        )}
      </Group>
      {!props.full.length ? (
        <Text size="sm" c="dimmed">
          {t("finance.charts.noData")}
        </Text>
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
