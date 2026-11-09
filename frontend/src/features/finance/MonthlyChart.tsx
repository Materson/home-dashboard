import { useMemo } from "react";
import { BarChart } from "@mantine/charts";
import { Paper, Stack, Title } from "@mantine/core";
import type { MonthlyTotal } from "./api";

/**
 * Stacked bar — expense vs income per month. We only render the first
 * currency we see; a multi-currency UI can come later.
 */
export function MonthlyChart({ totals }: { totals: MonthlyTotal[] }) {
  const { data, currency } = useMemo(() => reshape(totals), [totals]);

  if (!data.length) {
    return (
      <Paper withBorder p="md">
        <Title order={5}>Monthly totals</Title>
      </Paper>
    );
  }

  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Title order={5}>Monthly totals ({currency})</Title>
        <BarChart
          h={220}
          data={data}
          dataKey="month"
          type="default"
          withLegend
          series={[
            { name: "expense", color: "red.6" },
            { name: "income", color: "teal.6" },
          ]}
        />
      </Stack>
    </Paper>
  );
}

function reshape(totals: MonthlyTotal[]): {
  data: { month: string; expense: number; income: number }[];
  currency: string;
} {
  const firstCurrency = totals[0]?.currency ?? "PLN";
  const only = totals.filter((t) => t.currency === firstCurrency);
  const byMonth = new Map<string, { month: string; expense: number; income: number }>();
  for (const row of only) {
    const entry = byMonth.get(row.year_month) ?? {
      month: row.year_month,
      expense: 0,
      income: 0,
    };
    if (row.kind === "expense") entry.expense = Number(row.total);
    else if (row.kind === "income") entry.income = Number(row.total);
    byMonth.set(row.year_month, entry);
  }
  return {
    data: [...byMonth.values()].sort((a, b) => a.month.localeCompare(b.month)),
    currency: firstCurrency,
  };
}
