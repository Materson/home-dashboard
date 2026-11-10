/**
 * Cars — pick a car, see its status at a glance (odometer, oil, inspection,
 * insurance, consumption, costs), and manage its records in tabs.
 */
import { useEffect, useState } from "react";
import {
  ActionIcon,
  Alert,
  Button,
  Group,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { LineChart } from "@mantine/charts";
import { MonthPickerInput } from "@mantine/dates";
import {
  IconArchive,
  IconArchiveOff,
  IconChevronLeft,
  IconChevronRight,
  IconPencil,
  IconPlus,
} from "@tabler/icons-react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import i18n from "@/i18n";
import { fmtDate, fmtMoney, fmtNumber, isoDate, parseIsoDate } from "@/lib/format";

import { carsApi, type Car, type CarSummary } from "./api";
import { CarModal } from "./CarModal";
import { RECORD_TABS } from "./records";
import { OdometerSection } from "./OdometerSection";
import { RecordSection } from "./RecordSection";
import { ServiceSection } from "./ServiceSection";

const SOON_KM = 1000;
const SOON_DAYS = 30;

export function CarsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [showArchived, setShowArchived] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [modal, setModal] = useState<{ open: boolean; car: Car | null }>({ open: false, car: null });

  const cars = useQuery({
    queryKey: ["cars", "list", showArchived],
    queryFn: () => carsApi.list(showArchived),
  });
  const car = cars.data?.find((c) => c.id === selectedId) ?? cars.data?.[0] ?? null;
  useEffect(() => {
    if (car && car.id !== selectedId) setSelectedId(car.id);
  }, [car, selectedId]);

  // Month whose costs the cost tile shows; the other tiles are always "now".
  const [month, setMonth] = useState(() => firstOfMonth(new Date()));
  const summary = useQuery({
    queryKey: ["cars", car?.id, "summary", isoDate(month)],
    queryFn: () => carsApi.summary(car!.id, isoDate(month)),
    enabled: !!car,
    placeholderData: keepPreviousData, // no flicker while stepping months
  });

  const archive = useMutation({
    mutationFn: (c: Car) => carsApi.setArchived(c.id, !c.archived),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cars"] }),
  });

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group>
          <Title order={2}>{t("nav.cars")}</Title>
          {!!cars.data?.length && (
            <Select
              data={cars.data.map((c) => ({
                value: c.id,
                label: c.archived ? `${c.name} (${t("cars.archived")})` : c.name,
              }))}
              value={car?.id ?? null}
              onChange={setSelectedId}
              allowDeselect={false}
              w={240}
            />
          )}
          {car && (
            <>
              <Button
                variant="subtle"
                size="xs"
                leftSection={<IconPencil size={14} />}
                onClick={() => setModal({ open: true, car })}
              >
                {t("finance.action.edit")}
              </Button>
              <Button
                variant="subtle"
                size="xs"
                color="gray"
                leftSection={car.archived ? <IconArchiveOff size={14} /> : <IconArchive size={14} />}
                onClick={() => archive.mutate(car)}
              >
                {t(car.archived ? "cars.unarchive" : "cars.archive")}
              </Button>
            </>
          )}
        </Group>
        <Group>
          <Switch
            label={t("cars.showArchived")}
            checked={showArchived}
            onChange={(e) => setShowArchived(e.currentTarget.checked)}
          />
          <Button leftSection={<IconPlus size={16} />} onClick={() => setModal({ open: true, car: null })}>
            {t("cars.addCar")}
          </Button>
        </Group>
      </Group>

      {cars.isSuccess && !cars.data.length && <Alert color="gray">{t("cars.empty")}</Alert>}

      {car && summary.data && (
        <Stack gap="xs">
          <PeriodSwitcher month={month} onChange={setMonth} />
          <SummaryTiles s={summary.data} />
        </Stack>
      )}
      {car && summary.data && summary.data.consumption.length > 1 && (
        <ConsumptionChart s={summary.data} />
      )}

      {car && (
        <Paper withBorder p="md">
          <Tabs defaultValue="fuel" keepMounted={false}>
            <Tabs.List>
              {RECORD_TABS.map((tab) => (
                <Tabs.Tab key={tab.key} value={tab.key}>
                  {t(tab.labelKey)}
                </Tabs.Tab>
              ))}
            </Tabs.List>
            {RECORD_TABS.map((tab) => (
              <Tabs.Panel key={tab.key} value={tab.key} pt="md">
                {tab.key === "odometer" ? (
                  <OdometerSection carId={car.id} />
                ) : tab.key === "service" ? (
                  <ServiceSection carId={car.id} />
                ) : (
                  <RecordSection carId={car.id} kind={tab.key} />
                )}
              </Tabs.Panel>
            ))}
          </Tabs>
        </Paper>
      )}

      <CarModal
        opened={modal.open}
        car={modal.car}
        onClose={() => setModal({ open: false, car: null })}
        onSaved={(c) => setSelectedId(c.id)}
      />
    </Stack>
  );
}

function Tile({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <Paper withBorder p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="xl" fw={700} c={color}>
        {value}
      </Text>
      {sub && (
        <Text size="xs" c="dimmed">
          {sub}
        </Text>
      )}
    </Paper>
  );
}

function firstOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function monthLabel(d: Date): string {
  return d.toLocaleDateString(i18n.language, { month: "long", year: "numeric" });
}

/** ‹ listopad 2026 › — steps the cost tile's month; the picker also jumps years. */
function PeriodSwitcher({ month, onChange }: { month: Date; onChange: (d: Date) => void }) {
  const { t } = useTranslation();
  const shift = (n: number) => onChange(new Date(month.getFullYear(), month.getMonth() + n, 1));
  const isCurrent = month.getTime() === firstOfMonth(new Date()).getTime();
  return (
    <Group gap={4} justify="flex-end">
      <Text size="sm" c="dimmed" mr="xs">
        {t("cars.sum.costsFor")}
      </Text>
      <ActionIcon variant="subtle" aria-label={t("cars.sum.prevMonth")} onClick={() => shift(-1)}>
        <IconChevronLeft size={18} />
      </ActionIcon>
      <MonthPickerInput
        size="xs"
        w={150}
        valueFormat="MMMM YYYY"
        value={month}
        onChange={(d) => d && onChange(firstOfMonth(d))}
      />
      <ActionIcon variant="subtle" aria-label={t("cars.sum.nextMonth")} onClick={() => shift(1)}>
        <IconChevronRight size={18} />
      </ActionIcon>
      {!isCurrent && (
        <Button size="xs" variant="subtle" onClick={() => onChange(firstOfMonth(new Date()))}>
          {t("cars.sum.thisMonth")}
        </Button>
      )}
    </Group>
  );
}

function SummaryTiles({ s }: { s: CarSummary }) {
  const { t } = useTranslation();
  const oil = s.oil;
  const oilColor =
    oil?.km_left == null ? undefined : oil.km_left < 0 ? "red" : oil.km_left < SOON_KM ? "orange" : undefined;
  const deadline = (kind: "inspection" | "insurance") => s.deadlines.find((d) => d.kind === kind);
  const deadlineTile = (kind: "inspection" | "insurance") => {
    const d = deadline(kind);
    return (
      <Tile
        key={kind}
        label={t(`cars.deadlineKind.${kind}`)}
        value={d ? fmtDate(d.valid_until) : "—"}
        sub={
          d
            ? d.days_left < 0
              ? t("cars.sum.expiredAgo", { days: -d.days_left })
              : t("cars.sum.daysLeft", { days: d.days_left })
            : t("cars.sum.noRecord")
        }
        color={d ? (d.days_left < 0 ? "red" : d.days_left < SOON_DAYS ? "orange" : undefined) : undefined}
      />
    );
  };

  return (
    <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
      <Tile
        label={t("cars.sum.odometer")}
        value={`${fmtNumber(s.current_km)} km`}
        sub={s.daily_km ? t("cars.sum.perDay", { km: fmtNumber(s.daily_km) }) : undefined}
      />
      <Tile
        label={t("cars.sum.oil")}
        value={
          oil?.km_left == null
            ? "—"
            : oil.km_left < 0
              ? t("cars.sum.overdueKm", { km: fmtNumber(-oil.km_left) })
              : `${fmtNumber(oil.km_left)} km`
        }
        sub={
          oil?.due_by
            ? t("cars.sum.dueBy", { date: fmtDate(oil.due_by) })
            : oil
              ? undefined
              : t("cars.sum.noRecord")
        }
        color={oilColor}
      />
      {deadlineTile("inspection")}
      {deadlineTile("insurance")}
      <Tile
        label={t("cars.sum.consumption")}
        value={s.last_consumption ? `${fmtNumber(s.last_consumption, 1)} l` : "—"}
        sub={s.avg_consumption ? t("cars.sum.avgConsumption", { value: fmtNumber(s.avg_consumption, 1) }) : undefined}
      />
      <Tile
        label={t("cars.sum.fuelInMonth", { month: monthLabel(parseIsoDate(s.period_month)) })}
        value={fmtMoney(s.fuel_cost_month)}
        sub={[
          Number(s.fuel_discounts_year) > 0
            ? t("cars.sum.discountsInYear", {
                year: s.period_month.slice(0, 4),
                value: fmtMoney(s.fuel_discounts_year),
              })
            : null,
          t("cars.sum.costsInYear", {
            year: s.period_month.slice(0, 4),
            value: fmtMoney(s.costs_year),
          }),
        ]
          .filter(Boolean)
          .join(" · ")}
      />
    </SimpleGrid>
  );
}

function ConsumptionChart({ s }: { s: CarSummary }) {
  const { t } = useTranslation();
  const data = s.consumption.map((p) => ({ date: fmtDate(p.date), value: Number(p.litres_per_100km) }));
  return (
    <Paper withBorder p="md">
      <Title order={5} mb="sm">
        {t("cars.chart.consumption")}
      </Title>
      <LineChart
        h={200}
        data={data}
        dataKey="date"
        series={[{ name: "value", label: t("cars.chart.l100km"), color: "indigo.6" }]}
        curveType="monotone"
        unit=" l"
      />
    </Paper>
  );
}
