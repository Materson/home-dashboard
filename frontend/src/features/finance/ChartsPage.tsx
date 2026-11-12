/**
 * Finanse → Wykresy: income vs expenses over 12 months (line), and for the
 * chosen period expenses / income per category and expenses per person
 * (pies — many categories are folded into "Pozostałe", the full list sits
 * next to each pie). "Dla kogo" narrows everything to one person's parts of
 * split transactions, or to the household's unsplit spending.
 */
import { useState } from "react";
import { DonutChart, LineChart } from "@mantine/charts";
import {
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
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { peopleApi } from "@/features/people/api";
import { fmtMoney } from "@/lib/format";

import { financeApi, type Slice } from "./api";
import { monthlyLine, type PeriodMode, periodRange, type PieSlice, topSlices } from "./chartData";

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
  const expenses = useQuery({
    queryKey: ["finance", "charts", "cat", "expense", from, to, person],
    queryFn: () => financeApi.categoryTotals(from, to, "expense", person),
  });
  const income = useQuery({
    queryKey: ["finance", "charts", "cat", "income", from, to, person],
    queryFn: () => financeApi.categoryTotals(from, to, "income", person),
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
      <Group justify="space-between">
        <Title order={2}>{t("finance.charts.title")}</Title>
        <Group>
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
        </Group>
      </Group>

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
        <Grid.Col span={{ base: 12, lg: person ? 6 : 4 }}>
          <PieCard title={t("finance.charts.expensesByCategory")} slices={topSlices(expenses.data ?? [], KEEP, other)} full={expenses.data ?? []} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: person ? 6 : 4 }}>
          <PieCard title={t("finance.charts.incomeByCategory")} slices={topSlices(income.data ?? [], KEEP, other)} full={income.data ?? []} />
        </Grid.Col>
        {!person && (
          <Grid.Col span={{ base: 12, lg: 4 }}>
            <PieCard
              title={t("finance.charts.expensesByPerson")}
              slices={topSlices(byPerson.data ?? [], KEEP, other, shared)}
              full={byPerson.data ?? []}
              sharedLabel={shared}
            />
          </Grid.Col>
        )}
      </Grid>
    </Stack>
  );
}

function PieCard(props: { title: string; slices: PieSlice[]; full: Slice[]; sharedLabel?: string }) {
  const { t } = useTranslation();
  const total = props.full.reduce((n, s) => n + Number(s.total), 0);
  return (
    <Paper withBorder p="md" h="100%">
      <Title order={5} mb="sm">
        {props.title}
      </Title>
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
                {props.full.map((s) => (
                  <Table.Tr key={s.key}>
                    <Table.Td>
                      <Group gap={6} wrap="nowrap">
                        <div style={{ width: 10, height: 10, borderRadius: 2, background: s.color, flexShrink: 0 }} />
                        <Text size="sm" truncate>
                          {s.key === "shared" ? props.sharedLabel : s.label}
                        </Text>
                      </Group>
                    </Table.Td>
                    <Table.Td ta="right">{fmtMoney(s.total, "PLN")}</Table.Td>
                    <Table.Td ta="right" c="dimmed" w={50}>
                      {total ? Math.round((Number(s.total) / total) * 100) : 0}%
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea.Autosize>
        </Stack>
      )}
    </Paper>
  );
}
