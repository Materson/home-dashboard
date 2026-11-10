import { useMemo } from "react";
import { BarChart } from "@mantine/charts";
import { Paper, Stack, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import type { MonthlyTotal } from "./api";

type Bar = { month: string; expense: number; income: number };

/**
 * Expense vs income per month for the `months` months ending with
 * `endMonth`. Months without transactions render as zero-height bars so the
 * x-axis always shows the full window. Only the first currency seen is
 * plotted; a multi-currency view can come later.
 */
export function MonthlyChart({
  totals,
  endMonth,
  months,
}: {
  totals: MonthlyTotal[];
  endMonth: Date;
  months: number;
}) {
  const { t } = useTranslation();
  const { data, currency } = useMemo(
    () => reshape(totals, endMonth, months),
    [totals, endMonth, months],
  );

  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Title order={5}>{t("finance.chart.title", { months, currency })}</Title>
        <BarChart
          h={220}
          data={data}
          dataKey="month"
          type="default"
          withLegend
          series={[
            { name: "expense", label: t("finance.chart.expense"), color: "red.6" },
            { name: "income", label: t("finance.chart.income"), color: "teal.6" },
          ]}
        />
      </Stack>
    </Paper>
  );
}

function reshape(
  totals: MonthlyTotal[],
  endMonth: Date,
  months: number,
): { data: Bar[]; currency: string } {
  const currency = totals[0]?.currency ?? "PLN";

  // Pre-fill every month in the window so gaps show as empty bars.
  const byMonth = new Map<string, Bar>();
  for (let i = months - 1; i >= 0; i--) {
    const d = new Date(endMonth.getFullYear(), endMonth.getMonth() - i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    byMonth.set(key, { month: key, expense: 0, income: 0 });
  }

  for (const row of totals) {
    if (row.currency !== currency) continue;
    const entry = byMonth.get(row.year_month);
    if (!entry) continue;
    if (row.kind === "expense") entry.expense = Number(row.total);
    else if (row.kind === "income") entry.income = Number(row.total);
  }
  return { data: [...byMonth.values()], currency };
}
