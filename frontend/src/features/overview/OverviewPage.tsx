/**
 * The start page: a greeting, tiles with this month's money, investments
 * and the nearest car deadline, then my next reminders, where this month's
 * money went and what runs out at home. Each part shows only with access
 * to its module (a child sees reminders and home, no money).
 */
import type { ReactNode } from "react";
import { DonutChart } from "@mantine/charts";
import { Anchor, Grid, Group, Paper, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconCar, IconScale, IconShoppingCart, IconTrendingUp, IconWallet } from "@tabler/icons-react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { useMe } from "@/features/auth/useMe";
import { usePermissions } from "@/features/auth/usePermissions";
import { carsApi } from "@/features/cars/api";
import { financeApi } from "@/features/finance/api";
import { distinctColors, topSlices } from "@/features/finance/chartData";
import { StockTile } from "@/features/household/StockTile";
import { INVESTMENTS_KEY, investmentsApi } from "@/features/investments/api";
import { UpcomingTile } from "@/features/notes/UpcomingTile";
import { fmtMoney, fmtNumber, isoDate } from "@/lib/format";

const DAY = 86_400_000;

function greetingKey(hour: number): string {
  if (hour >= 5 && hour < 12) return "overview.hello.morning";
  if (hour >= 12 && hour < 18) return "overview.hello.afternoon";
  return "overview.hello.evening";
}

export function OverviewPage() {
  const { t, i18n } = useTranslation();
  const me = useMe().data;
  const perms = usePermissions();
  const now = new Date();
  const name = me?.first_name || me?.email.split("@")[0] || "";
  const finance = perms.canView("finance");

  return (
    <Stack gap="xl">
      <PageHeader
        title={t(greetingKey(now.getHours()), { name })}
        subtitle={now.toLocaleDateString(i18n.language, { weekday: "long", day: "numeric", month: "long" })}
      />
      <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md">
        {finance && <MoneyTiles />}
        {finance && <InvestmentsTile />}
        {perms.canView("cars") && <CarTile />}
      </SimpleGrid>
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, md: finance ? 7 : 12 }}>
          <Card title={t("overview.upcomingReminders")}>
            <UpcomingTile />
          </Card>
        </Grid.Col>
        {finance && (
          <Grid.Col span={{ base: 12, md: 5 }}>
            <SpendCard />
          </Grid.Col>
        )}
        {perms.canView("household") && (
          <Grid.Col span={12}>
            <Card title={t("overview.stock")} icon={<IconShoppingCart size={18} />} link="/household">
              <StockTile />
            </Card>
          </Grid.Col>
        )}
      </Grid>
    </Stack>
  );
}

function Card(props: { title: string; icon?: ReactNode; link?: string; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <Paper withBorder p="lg" h="100%">
      <Group justify="space-between" mb="md">
        <Group gap="xs">
          {props.icon && (
            <ThemeIcon variant="light" size="md" radius="md">
              {props.icon}
            </ThemeIcon>
          )}
          <Title order={4}>{props.title}</Title>
        </Group>
        {props.link && (
          <Anchor component={Link} to={props.link} size="sm">
            {t("overview.seeAll")}
          </Anchor>
        )}
      </Group>
      {props.children}
    </Paper>
  );
}

function StatTile(props: {
  icon: ReactNode;
  color: string;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  subColor?: string;
  to: string;
}) {
  return (
    <Paper
      withBorder
      p="lg"
      component={Link}
      to={props.to}
      style={{ textDecoration: "none", color: "inherit", display: "block" }}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Text size="sm" c="dimmed" fw={500}>
          {props.label}
        </Text>
        <ThemeIcon variant="light" color={props.color} size={34} radius="md">
          {props.icon}
        </ThemeIcon>
      </Group>
      <Text fz={26} fw={700} lh={1.2} mt={4} style={{ fontVariantNumeric: "tabular-nums" }}>
        {props.value}
      </Text>
      {props.sub && (
        <Text size="xs" c={props.subColor ?? "dimmed"} mt={6} fw={props.subColor ? 600 : undefined}>
          {props.sub}
        </Text>
      )}
    </Paper>
  );
}

function monthStart(offset = 0): Date {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth() + offset, 1);
}

function MoneyTiles() {
  const { t } = useTranslation();
  const thisMonth = isoDate(monthStart()).slice(0, 7);
  const lastMonth = isoDate(monthStart(-1)).slice(0, 7);
  const totals = useQuery({
    queryKey: ["finance", "overview", "totals", thisMonth],
    queryFn: () => financeApi.monthlyTotals(isoDate(monthStart()), 2),
  });
  const sum = (month: string, kind: string) =>
    (totals.data ?? [])
      .filter((r) => r.year_month === month && r.kind === kind && r.currency === "PLN")
      .reduce((n, r) => n + Number(r.total), 0);
  const spent = sum(thisMonth, "expense");
  const earned = sum(thisMonth, "income");
  const balance = earned - spent;
  return (
    <>
      <StatTile
        icon={<IconWallet size={19} />}
        color="red"
        label={t("overview.spentThisMonth")}
        value={totals.isSuccess ? fmtMoney(spent.toFixed(2)) : "—"}
        sub={t("overview.lastMonth", { amount: fmtMoney(sum(lastMonth, "expense").toFixed(2)) })}
        to="/finance"
      />
      <StatTile
        icon={<IconScale size={19} />}
        color={balance >= 0 ? "teal" : "red"}
        label={t("overview.balanceThisMonth")}
        value={totals.isSuccess ? `${balance > 0 ? "+" : ""}${fmtMoney(balance.toFixed(2))}` : "—"}
        sub={t("overview.earned", { amount: fmtMoney(earned.toFixed(2)) })}
        to="/finance/charts"
      />
    </>
  );
}

function InvestmentsTile() {
  const { t, i18n } = useTranslation();
  const assets = useQuery({ queryKey: [...INVESTMENTS_KEY, "assets"], queryFn: investmentsApi.assets });
  const list = assets.data ?? [];
  const value = list.reduce((n, a) => n + Number(a.value), 0);
  const cost = list.reduce((n, a) => n + Number(a.cost), 0);
  const gain = list.reduce((n, a) => n + Number(a.gain), 0);
  const pct = cost ? (gain / cost) * 100 : 0;
  const sign = gain > 0 ? "+" : "";
  return (
    <StatTile
      icon={<IconTrendingUp size={19} />}
      color="violet"
      label={t("nav.investments")}
      value={assets.isSuccess ? fmtMoney(value.toFixed(2)) : "—"}
      sub={
        list.length
          ? `${sign}${fmtMoney(gain.toFixed(2))} (${sign}${pct.toLocaleString(i18n.language, { maximumFractionDigits: 1 })}%)`
          : t("overview.noInvestments")
      }
      subColor={list.length ? (gain >= 0 ? "teal" : "red") : undefined}
      to="/finance/investments"
    />
  );
}

/** The nearest deadline of any car: inspection, insurance, other or the oil change. */
function CarTile() {
  const { t } = useTranslation();
  const month = isoDate(monthStart());
  const cars = useQuery({ queryKey: ["cars", "list", false], queryFn: () => carsApi.list(false) });
  const summaries = useQueries({
    queries: (cars.data ?? []).map((car) => ({
      queryKey: ["cars", car.id, "summary", month],
      queryFn: () => carsApi.summary(car.id, month),
    })),
  });
  const today = new Date(new Date().toDateString()).getTime();
  const due = (cars.data ?? []).flatMap((car, i) => {
    const s = summaries[i]?.data;
    if (!s) return [];
    const out = s.deadlines.map((d) => ({ car: car.name, what: t(`cars.deadlineKind.${d.kind}`), days: d.days_left }));
    if (s.oil?.due_by) {
      const days = Math.round((new Date(`${s.oil.due_by}T00:00:00`).getTime() - today) / DAY);
      out.push({ car: car.name, what: t("overview.oilChange"), days });
    }
    return out;
  });
  const next = due.sort((a, b) => a.days - b.days)[0];
  return (
    <StatTile
      icon={<IconCar size={19} />}
      color={!next ? "blue" : next.days < 0 ? "red" : next.days <= 30 ? "orange" : "blue"}
      label={t("overview.nextCarDeadline")}
      value={
        !next
          ? "—"
          : next.days < 0
            ? t("overview.overdueDays", { count: -next.days })
            : next.days === 0
              ? t("overview.today")
              : t("overview.inDays", { count: next.days })
      }
      sub={next ? `${next.what} · ${next.car}` : t("overview.noCarDeadlines")}
      to="/cars"
    />
  );
}

function SpendCard() {
  const { t } = useTranslation();
  const from = isoDate(monthStart());
  const to = isoDate(new Date(monthStart(1).getTime() - DAY));
  const slices = useQuery({
    queryKey: ["finance", "charts", "cat", "expense", from, to, null, undefined],
    queryFn: () => financeApi.categoryTotals(from, to, "expense"),
  });
  const full = distinctColors(slices.data ?? []);
  const pie = topSlices(full, 5, t("finance.charts.other"));
  const total = full.reduce((n, s) => n + Number(s.total), 0);
  return (
    <Card title={t("overview.spend")} icon={<IconWallet size={18} />} link="/finance/charts">
      {!full.length ? (
        <Text size="sm" c="dimmed">
          {t("finance.charts.noData")}
        </Text>
      ) : (
        <Group gap="lg" wrap="nowrap" align="center">
          <DonutChart
            data={pie.map(({ name, value, color }) => ({ name, value, color }))}
            size={140}
            thickness={20}
            withTooltip={false}
            chartLabel={`${fmtNumber(total)} PLN`}
          />
          <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
            {pie.map((s) => (
              <Group key={s.key} gap={8} wrap="nowrap" justify="space-between">
                <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
                  <div style={{ width: 10, height: 10, borderRadius: 3, background: s.color, flexShrink: 0 }} />
                  <Text size="sm" truncate>
                    {s.name}
                  </Text>
                </Group>
                <Text size="sm" fw={600} style={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                  {Math.round((s.value / total) * 100)}%
                </Text>
              </Group>
            ))}
          </Stack>
        </Group>
      )}
    </Card>
  );
}
