/**
 * Finanse → Inwestycje: what's held, what it's worth, and how that changed.
 * Gold (NBP) and crypto (CoinGecko) are priced daily; bonds are computed
 * from their rules and GUS inflation; stocks and others are valued by hand.
 * Click an asset for its chart, purchases, bond periods and values.
 * Amounts are kept in PLN; the PLN / USD / EUR switch shows them in another
 * currency at the latest NBP rate.
 */
import { createContext, useContext, useState } from "react";
import { DonutChart, LineChart } from "@mantine/charts";
import {
  ActionIcon,
  Badge,
  Button,
  Drawer,
  Grid,
  Group,
  NumberInput,
  Paper,
  Popover,
  SegmentedControl,
  SimpleGrid,
  Switch,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconArchive,
  IconCash,
  IconPencil,
  IconPercentage,
  IconPlus,
  IconRefresh,
  IconTrash,
  IconUsers,
} from "@tabler/icons-react";
import { DatePickerInput } from "@mantine/dates";
import { useLocalStorage } from "@mantine/hooks";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";
import { ChoiceTabs } from "@/components/ChoiceTabs";
import { useRangeSelect } from "@/components/useRangeSelect";

import { usePermissions } from "@/features/auth/usePermissions";
import { fmtDate, fmtMoney, fmtNumber, fmtQty, isoDate, parseIsoDate } from "@/lib/format";

import {
  type Asset,
  type AssetKind,
  type Currency,
  type Gain,
  INVESTMENTS_KEY,
  investmentsApi,
  type Lot,
  type Point,
} from "./api";
import { AssetModal, InflationModal, LotModal, SellModal, ValueModal } from "./forms";

const KIND_COLOR: Record<AssetKind, string> = {
  gold: "yellow.6",
  silver: "gray.5",
  crypto: "orange.6",
  stock: "blue.6",
  bond: "teal.6",
  other: "gray.6",
};
const RANGES = [
  { value: "all", months: null },
  { value: "12", months: 12 },
  { value: "36", months: 36 },
  { value: "range", months: null },
];
const KINDS: AssetKind[] = ["gold", "silver", "crypto", "stock", "bond", "other"];

const CURRENCIES: Currency[] = ["PLN", "USD", "EUR"];

/** Shows PLN amounts in the picked currency: ``rate`` = PLN for 1 unit of it. */
function makeMoney(currency: Currency, rate: number) {
  const conv = (v: string | number) => Number(v) / rate;
  return {
    currency,
    conv,
    /** A PLN amount, converted and formatted. */
    fmt: (v: string | number) => fmtMoney(conv(v).toFixed(2), currency),
    /** An amount already in ``currency`` (chart points), formatted. */
    show: (v: string | number) => fmtMoney(Number(v).toFixed(2), currency),
  };
}
type Money = ReturnType<typeof makeMoney>;
const MoneyContext = createContext<Money>(makeMoney("PLN", 1));
const useMoney = () => useContext(MoneyContext);

const gainColor = (v: string) => (Number(v) > 0 ? "teal" : Number(v) < 0 ? "red" : undefined);

function chartData(points: Point[]) {
  return points.map((p) => ({ date: fmtDate(p.date), value: Number(p.value), cost: Number(p.cost) }));
}

export function InvestmentsPage() {
  const { t } = useTranslation();
  const canEdit = usePermissions().canEdit("finance");
  // Default: the whole history, all kinds.
  const [range, setRange] = useState("all");
  const [kind, setKind] = useState<AssetKind | "all">("all");
  const [picking, setPicking] = useState<[Date | null, Date | null]>([null, null]);
  const [dates, setDates] = useState<[Date, Date] | null>(null);
  const months = RANGES.find((r) => r.value === range)?.months ?? null;
  const custom = range === "range" && dates ? { from: isoDate(dates[0]), to: isoDate(dates[1]) } : {};
  // Leave sold / closed positions out of the chart and the list.
  const [openOnly, setOpenOnly] = useState(false);
  const filters = { months, kind: kind === "all" ? null : kind, openOnly, ...custom };
  const [form, setForm] = useState<Asset | null | "new">(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [inflationOpen, setInflationOpen] = useState(false);
  const [currency, setCurrency] = useLocalStorage<Currency>({
    key: "investments.currency",
    defaultValue: "PLN",
    getInitialValueInEffect: false,
  });
  const fx = useQuery({
    queryKey: [...INVESTMENTS_KEY, "fx"],
    queryFn: investmentsApi.fx,
    enabled: currency !== "PLN",
    staleTime: 3_600_000,
    retry: 1,
  });
  const rate = currency === "PLN" ? 1 : Number(fx.data?.rates[currency] ?? 0);
  // Until the rate is known (or if NBP can't be reached) amounts stay in PLN.
  const money = rate > 0 ? makeMoney(currency, rate) : makeMoney("PLN", 1);

  const assets = useQuery({ queryKey: [...INVESTMENTS_KEY, "assets"], queryFn: investmentsApi.assets });
  const portfolio = useQuery({
    queryKey: [...INVESTMENTS_KEY, "portfolio", filters],
    queryFn: () => investmentsApi.portfolio(filters),
    placeholderData: keepPreviousData, // no flicker while changing the range
  });
  const p = portfolio.data;
  // With a date range the gains are those earned in it; otherwise since bought.
  const period = p?.period ?? null;
  const periodLabel = period ? `${fmtDate(period.start)} – ${fmtDate(period.end)}` : "";
  const kindsHeld = KINDS.filter((k) => (assets.data ?? []).some((a) => a.kind === k));
  const kindOptions: { value: AssetKind | "all"; label: string }[] = [
    { value: "all", label: t("investments.allKinds") },
    ...kindsHeld.map((k) => ({ value: k, label: t(`investments.kind.${k}`) })),
  ];
  const shown = (assets.data ?? []).filter(
    (a) => (kind === "all" || a.kind === kind) && (!openOnly || Number(a.quantity) > 0),
  );
  const qc = useQueryClient();
  const refresh = useMutation({
    mutationFn: investmentsApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: INVESTMENTS_KEY }),
  });
  const opened = assets.data?.find((a) => a.id === openId) ?? null;
  const pie = Object.entries(p?.by_kind ?? {})
    .filter(([, v]) => Number(v) > 0)
    .map(([k, v]) => ({ name: t(`investments.kind.${k}`), value: Number(v), color: KIND_COLOR[k as AssetKind] }));

  return (
    <MoneyContext.Provider value={money}>
    <Stack gap="lg">
      <PageHeader
        title={t("investments.title")}
        subtitle={t("page.investments.subtitle")}
        actions={
        <>
          <SegmentedControl
            value={currency}
            onChange={(v) => setCurrency(v as Currency)}
            data={CURRENCIES}
            aria-label={t("investments.currency")}
          />
          {canEdit && (
            <Tooltip label={t("investments.refreshHint")}>
              <Button variant="default" leftSection={<IconRefresh size={16} />} loading={refresh.isPending} onClick={() => refresh.mutate()}>
                {t("investments.refresh")}
              </Button>
            </Tooltip>
          )}
          <Button variant="light" leftSection={<IconPercentage size={16} />} onClick={() => setInflationOpen(true)}>
            {t("investments.inflation.title")}
          </Button>
          {canEdit && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setForm("new")}>
              {t("investments.add")}
            </Button>
          )}
        </>
        }
      />

      {currency !== "PLN" && (
        <Text size="xs" c={fx.isError ? "orange" : "dimmed"} mt={-8}>
          {fx.isError
            ? t("investments.fxError")
            : fx.data && rate > 0
              ? t("investments.fxNote", {
                  currency,
                  date: fmtDate(fx.data.date),
                  rate: fmtNumber(rate, 4),
                })
              : t("investments.fxLoading")}
        </Text>
      )}
      {refresh.data && refresh.data.errors > 0 && (
        <Text size="sm" c="orange">
          {t("investments.refreshErrors")}
        </Text>
      )}
      {kindsHeld.length > 1 && (
        <ChoiceTabs
          label={t("investments.kindFilter")}
          value={kind}
          onChange={setKind}
          data={kindOptions}
          style={{ alignSelf: "flex-start" }}
        />
      )}
      {p && (
        <SimpleGrid cols={{ base: 1, xs: 3 }}>
          <Tile label={t("investments.value")} value={money.fmt(p.value)} />
          <Tile label={t("investments.cost")} value={money.fmt(p.cost)} />
          {period ? (
            <Tile
              label={t("investments.gainInPeriod")}
              value={money.fmt(period.gain)}
              color={gainColor(period.gain)}
              sub={[period.gain_pct != null ? `${period.gain_pct}%` : null, periodLabel].filter(Boolean).join(" · ")}
            />
          ) : (
            <Tile
              label={t("investments.gain")}
              value={money.fmt(p.gain)}
              color={gainColor(p.gain)}
              sub={Number(p.cost) ? `${((Number(p.gain) / Number(p.cost)) * 100).toFixed(1)}%` : undefined}
            />
          )}
        </SimpleGrid>
      )}

      <Grid>
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Paper withBorder p="md">
            <Group justify="space-between" mb="sm">
              <Title order={5}>{t("investments.chart")}</Title>
              <Group gap="xs">
                <Switch
                  size="xs"
                  label={t("investments.hideClosed")}
                  checked={openOnly}
                  onChange={(e) => setOpenOnly(e.currentTarget.checked)}
                />
                <ChoiceTabs
                  size="xs"
                  label={t("common.period")}
                  value={range}
                  onChange={setRange}
                  data={RANGES.map((r) => ({ value: r.value, label: t(`investments.range.${r.value}`) }))}
                />
                {range === "range" && (
                  <DatePickerInput
                    size="xs"
                    type="range"
                    allowSingleDateInRange
                    maxDate={new Date()}
                    valueFormat="DD.MM.YYYY"
                    placeholder={t("investments.pickRange")}
                    value={picking}
                    onChange={(v) => {
                      setPicking(v);
                      if (v[0] && v[1]) setDates([v[0], v[1]]);
                    }}
                    w={210}
                  />
                )}
              </Group>
            </Group>
            <ValueChart
              points={p?.series ?? []}
              // Dragging across the chart picks those dates as the range.
              onSelect={(from, to) => {
                const span: [Date, Date] = [parseIsoDate(from), parseIsoDate(to)];
                setPicking(span);
                setDates(span);
                setRange("range");
              }}
            />
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Paper withBorder p="md" h="100%">
            <Title order={5} mb="sm">
              {t("investments.byKind")}
            </Title>
            {pie.length ? (
              <Stack align="center">
                <DonutChart data={pie} size={180} thickness={28} withTooltip tooltipDataSource="segment" valueFormatter={money.fmt} />
                <Group gap="xs" justify="center">
                  {pie.map((s) => (
                    <Badge key={s.name} color={s.color} variant="light">
                      {s.name}: {money.fmt(s.value)}
                    </Badge>
                  ))}
                </Group>
              </Stack>
            ) : (
              <Text size="sm" c="dimmed">
                {t("investments.empty")}
              </Text>
            )}
          </Paper>
        </Grid.Col>
      </Grid>

      <Paper withBorder>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("investments.f.name")}</Table.Th>
              {/* Phones: kind, quantity and what was paid under the name. */}
              <Table.Th ta="right" visibleFrom="sm">{t("investments.held")}</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">{t("investments.cost")}</Table.Th>
              <Table.Th ta="right">{t("investments.value")}</Table.Th>
              <Table.Th ta="right">
                {period ? (
                  <Tooltip label={periodLabel}>
                    <span>{t("investments.gainInPeriod")}</span>
                  </Tooltip>
                ) : (
                  t("investments.gain")
                )}
              </Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {shown.map((a) => (
              <Table.Tr key={a.id} onClick={() => setOpenId(a.id)} style={{ cursor: "pointer" }}>
                <Table.Td>
                  <Group gap="xs" wrap="nowrap">
                    <Badge size="sm" color={KIND_COLOR[a.kind]} variant="light" visibleFrom="sm" style={{ flexShrink: 0 }}>
                      {t(`investments.kind.${a.kind}`)}
                    </Badge>
                    <Text fw={600}>{a.name}</Text>
                    {(a.shares.length > 0 || !a.is_owner) && (
                      <Tooltip label={a.is_owner ? t("investments.sharedWith", { names: a.shares.map((s) => s.name).join(", ") }) : t("investments.sharedBy", { name: a.owner_name })}>
                        <IconUsers size={14} color="var(--mantine-color-dimmed)" />
                      </Tooltip>
                    )}
                  </Group>
                  <Text size="xs" c="dimmed" hiddenFrom="sm">
                    {t(`investments.kind.${a.kind}`)} · {held(a, t)} · {t("investments.cost")}: {money.fmt(a.cost)}
                  </Text>
                </Table.Td>
                <Table.Td ta="right" visibleFrom="sm">{held(a, t)}</Table.Td>
                <Table.Td ta="right" visibleFrom="sm">{money.fmt(a.cost)}</Table.Td>
                <Table.Td ta="right">
                  <Text size="sm" fw={600}>
                    {money.fmt(a.value)}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {a.estimated ? t("investments.estimated") : a.price_date ? fmtDate(a.price_date) : ""}
                  </Text>
                </Table.Td>
                <GainCell g={period ? period.assets[a.id] : a} fmt={money.fmt} />
              </Table.Tr>
            ))}
            {assets.isSuccess && !assets.data.length && (
              <Table.Tr>
                <Table.Td colSpan={5} ta="center" c="dimmed" py="md">
                  {t("investments.empty")}
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      <AssetDrawer asset={opened} canEdit={canEdit && !!opened?.can_edit} onClose={() => setOpenId(null)} onEdit={(a) => setForm(a)} />
      <AssetModal asset={form} onClose={() => setForm(null)} />
      <InflationModal opened={inflationOpen} onClose={() => setInflationOpen(false)} />
    </Stack>
    </MoneyContext.Provider>
  );
}

/** A gain with its % (none when the asset isn't in the chosen period's data). */
function GainCell({ g, fmt }: { g: Gain | undefined; fmt: (v: string) => string }) {
  if (!g) return <Table.Td ta="right">—</Table.Td>;
  return (
    <Table.Td ta="right" c={gainColor(g.gain)}>
      {fmt(g.gain)}
      {g.gain_pct != null && <Text size="xs">{g.gain_pct}%</Text>}
    </Table.Td>
  );
}

function held(a: Asset, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (a.kind === "bond") return t("investments.bondsCount", { count: Number(a.quantity) });
  return `${fmtQty(a.quantity)} ${t(`investments.unit.${a.unit}`)}`;
}

function Tile(props: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <Paper withBorder p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {props.label}
      </Text>
      <Text size="xl" fw={700} c={props.color}>
        {props.value}
      </Text>
      {props.sub && (
        <Text size="xs" c={props.color ?? "dimmed"}>
          {props.sub}
        </Text>
      )}
    </Paper>
  );
}

/** Y-axis bounds around the data (a deposit growing 10 000 → 10 300 would be
 *  a flat line on an axis from 0). A little padding above and below. */
export function valueDomain(points: Point[]): [number, number] {
  const values = points.flatMap((p) => [Number(p.value), Number(p.cost)]);
  if (!values.length) return [0, 1];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo) * 0.1 || Math.max(Math.abs(hi) * 0.01, 1);
  return [Math.floor(Math.max(0, lo - pad)), Math.ceil(hi + pad)];
}

/** Value vs cost; with ``onSelect`` dragging across it picks a span of its
 *  dates (first and last, "YYYY-MM-DD"). */
function ValueChart({ points: pln, onSelect }: { points: Point[]; onSelect?: (from: string, to: string) => void }) {
  const { t } = useTranslation();
  const money = useMoney();
  const points = pln.map((p) => ({ ...p, value: String(money.conv(p.value)), cost: String(money.conv(p.cost)) }));
  const data = chartData(points);
  const drag = useRangeSelect(
    data.map((d) => d.date),
    onSelect && ((i, j) => onSelect(points[i].date, points[j].date)),
  );
  if (!points.length) {
    return (
      <Text size="sm" c="dimmed">
        {t("investments.noHistory")}
      </Text>
    );
  }
  return (
    <>
    <LineChart
      h={260}
      data={data}
      yAxisProps={{ domain: valueDomain(points), tickFormatter: (v: number) => fmtQty(String(Math.round(v))) }}
      dataKey="date"
      {...drag.chartProps}
      withLegend
      withDots={false}
      curveType="linear"
      valueFormatter={money.show}
      series={[
        { name: "value", label: t("investments.value"), color: "indigo.6" },
        { name: "cost", label: t("investments.cost"), color: "gray.5", strokeDasharray: "5 5" },
      ]}
    >
      {drag.area}
    </LineChart>
    {onSelect && points.length > 1 && (
      <Text size="xs" c="dimmed" mt="xs">
        {t("investments.dragHint")}
      </Text>
    )}
    </>
  );
}

/** An asset's whole history; dragging across it zooms in, a button shows
 *  all of it again. */
function AssetChart({ points }: { points: Point[] }) {
  const { t } = useTranslation();
  const [zoom, setZoom] = useState<{ from: string; to: string } | null>(null);
  const shown = zoom ? points.filter((p) => p.date >= zoom.from && p.date <= zoom.to) : points;
  return (
    <div>
      {zoom && (
        <Group justify="space-between" mb={4}>
          <Text size="xs" c="dimmed">
            {fmtDate(zoom.from)} – {fmtDate(zoom.to)}
          </Text>
          <Button size="compact-xs" variant="subtle" onClick={() => setZoom(null)}>
            {t("investments.wholeHistory")}
          </Button>
        </Group>
      )}
      <ValueChart points={shown} onSelect={(from, to) => setZoom({ from, to })} />
    </div>
  );
}

function AssetDrawer(props: { asset: Asset | null; canEdit: boolean; onClose: () => void; onEdit: (a: Asset) => void }) {
  const { t } = useTranslation();
  const money = useMoney();
  const qc = useQueryClient();
  const a = props.asset;
  const [lotForm, setLotForm] = useState<{ lot: Lot | null } | null>(null);
  // A sale of one purchase ({lot}), or of part of the holding ({lot: null}).
  const [selling, setSelling] = useState<{ lot: Lot | null } | null>(null);
  const [valueFor, setValueFor] = useState<Asset | null>(null);
  const [periodsFor, setPeriodsFor] = useState<string | null>(null);
  const series = useQuery({
    queryKey: [...INVESTMENTS_KEY, "series", a?.id],
    queryFn: () => investmentsApi.series(a!.id, null),
    enabled: !!a,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: INVESTMENTS_KEY });
  const removeLot = useMutation({ mutationFn: investmentsApi.deleteLot, onSuccess: refresh });
  const archive = useMutation({
    mutationFn: (id: string) => investmentsApi.archiveAsset(id),
    onSuccess: () => {
      refresh();
      props.onClose();
    },
  });
  const manual = a && (a.kind === "stock" || a.kind === "other");
  const deposit = a?.kind === "other" && a.rate != null;

  return (
    <Drawer opened={!!a} onClose={props.onClose} position="right" size="xl" title={a?.name ?? ""}>
      {a && (
        <Stack>
          <Group gap="xs">
            <Badge color={KIND_COLOR[a.kind]} variant="light">
              {t(`investments.kind.${a.kind}`)}
            </Badge>
            {a.symbol && <Badge variant="outline" color="gray">{a.symbol}</Badge>}
            {a.kind === "bond" && (
              <Text size="sm" c="dimmed">
                {t("investments.bondTerms", {
                  first: a.bond_first_rate,
                  margin: a.bond_margin ?? "—",
                })}
              </Text>
            )}
          </Group>
          <SimpleGrid cols={3}>
            <Tile label={t("investments.value")} value={money.fmt(a.value)} sub={a.estimated ? t("investments.estimated") : undefined} />
            <Tile label={t("investments.cost")} value={money.fmt(a.cost)} />
            <Tile label={t("investments.gain")} value={money.fmt(a.gain)} color={gainColor(a.gain)} sub={a.gain_pct != null ? `${a.gain_pct}%` : undefined} />
          </SimpleGrid>
          {Number(a.paid_out) > 0 && (
            <Text size="sm">{t("investments.paidOut", { amount: money.fmt(a.paid_out) })}</Text>
          )}
          {Number(a.realized) !== 0 && (
            <Text size="sm" c={gainColor(a.realized)}>
              {t("investments.realized", { amount: money.fmt(a.realized) })}
            </Text>
          )}
          <AssetChart key={a.id} points={series.data ?? []} />
          {a.kind === "crypto" && (
            <Text size="xs" c="dimmed">
              {t("investments.cryptoHistoryNote")}
            </Text>
          )}

          {props.canEdit && (
            <Group gap="xs">
              <Button size="xs" leftSection={<IconPlus size={14} />} onClick={() => setLotForm({ lot: null })}>
                {t("investments.addLot")}
              </Button>
              {Number(a.quantity) > 0 && !deposit && (
                <Button size="xs" variant="light" leftSection={<IconCash size={14} />} onClick={() => setSelling({ lot: null })}>
                  {t("investments.sell")}
                </Button>
              )}
              {manual && (
                <Button size="xs" variant="light" onClick={() => setValueFor(a)}>
                  {t("investments.setValue")}
                </Button>
              )}
              <Button size="xs" variant="light" leftSection={<IconPencil size={14} />} onClick={() => props.onEdit(a)}>
                {t("finance.action.edit")}
              </Button>
              {a.is_owner && (
              <Popover withArrow>
                <Popover.Target>
                  <Button size="xs" variant="subtle" color="gray" leftSection={<IconArchive size={14} />}>
                    {t("investments.archive")}
                  </Button>
                </Popover.Target>
                <Popover.Dropdown>
                  <Stack gap="xs" maw={240}>
                    <Text size="sm">{t("investments.archiveConfirm")}</Text>
                    <Button size="xs" color="red" onClick={() => archive.mutate(a.id)}>
                      {t("investments.archive")}
                    </Button>
                  </Stack>
                </Popover.Dropdown>
              </Popover>
              )}
            </Group>
          )}

          <Title order={6}>{t("investments.lots")}</Title>
          <Table fz="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("investments.f.boughtOn")}</Table.Th>
                <Table.Th ta="right">{t("investments.held")}</Table.Th>
                <Table.Th ta="right">{t("investments.f.paid")}</Table.Th>
                <Table.Th>{t("investments.f.soldOn")}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {a.lots.map((lot) => (
                <LotRow
                  key={lot.id}
                  asset={a}
                  lot={lot}
                  canEdit={props.canEdit}
                  showPeriods={periodsFor === lot.id}
                  onTogglePeriods={() => setPeriodsFor(periodsFor === lot.id ? null : lot.id)}
                  onEdit={() => setLotForm({ lot })}
                  onSell={() => setSelling({ lot })}
                  onDelete={() => removeLot.mutate(lot.id)}
                />
              ))}
            </Table.Tbody>
          </Table>
          <LotModal asset={a} lot={lotForm?.lot ?? null} opened={!!lotForm} onClose={() => setLotForm(null)} />
          <SellModal asset={a} lot={selling?.lot ?? null} opened={!!selling} onClose={() => setSelling(null)} />
          <ValueModal asset={valueFor} onClose={() => setValueFor(null)} />
        </Stack>
      )}
    </Drawer>
  );
}

function LotRow(props: {
  asset: Asset;
  lot: Lot;
  canEdit: boolean;
  showPeriods: boolean;
  onTogglePeriods: () => void;
  onEdit: () => void;
  onSell: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const money = useMoney();
  const { lot, asset } = props;
  return (
    <>
      <Table.Tr c={lot.sold_on ? "dimmed" : undefined}>
        <Table.Td>{fmtDate(lot.bought_on)}</Table.Td>
        <Table.Td ta="right">
          {asset.kind === "bond" ? t("investments.bondsCount", { count: Number(lot.quantity) }) : fmtQty(lot.quantity)}
        </Table.Td>
        <Table.Td ta="right">
          {money.fmt(lot.price_total)}
          {lot.price_currency !== "PLN" && lot.price_foreign != null && (
            <Text size="xs" c="dimmed">
              {t("investments.paidForeign", {
                amount: fmtMoney(lot.price_foreign, lot.price_currency),
                rate: fmtNumber(lot.price_rate, 4),
              })}
            </Text>
          )}
        </Table.Td>
        <Table.Td>
          {lot.sold_on ? `${fmtDate(lot.sold_on)} · ${money.fmt(lot.sold_amount ?? 0)}` : "—"}
          {lot.sold_on && lot.sold_currency !== "PLN" && lot.sold_foreign != null && (
            <Text size="xs" c="dimmed">
              {t("investments.paidForeign", {
                amount: fmtMoney(lot.sold_foreign, lot.sold_currency),
                rate: fmtNumber(lot.sold_rate, 4),
              })}
            </Text>
          )}
        </Table.Td>
        <Table.Td>
          <Group gap={2} justify="flex-end" wrap="nowrap">
            {asset.kind === "bond" && (
              <Button size="compact-xs" variant="subtle" onClick={props.onTogglePeriods}>
                {t("investments.periods")}
              </Button>
            )}
            {props.canEdit && !lot.sold_on && (
              <Tooltip label={t("investments.sell")}>
                <ActionIcon variant="subtle" onClick={props.onSell}>
                  <IconCash size={16} />
                </ActionIcon>
              </Tooltip>
            )}
            {props.canEdit && (
              <>
                <ActionIcon variant="subtle" onClick={props.onEdit} aria-label={t("finance.action.edit")}>
                  <IconPencil size={16} />
                </ActionIcon>
                <ActionIcon variant="subtle" color="red" onClick={props.onDelete} aria-label={t("finance.action.delete")}>
                  <IconTrash size={16} />
                </ActionIcon>
              </>
            )}
          </Group>
        </Table.Td>
      </Table.Tr>
      {props.showPeriods && (
        <Table.Tr>
          <Table.Td colSpan={5}>
            <BondPeriods lotId={lot.id} canEdit={props.canEdit} />
          </Table.Td>
        </Table.Tr>
      )}
    </>
  );
}

function BondPeriods({ lotId, canEdit }: { lotId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const periods = useQuery({ queryKey: [...INVESTMENTS_KEY, "periods", lotId], queryFn: () => investmentsApi.periods(lotId) });
  const override = useMutation({
    mutationFn: (v: { period: number; rate: string | null }) => investmentsApi.overrideRate(lotId, v.period, v.rate),
    onSuccess: () => qc.invalidateQueries({ queryKey: INVESTMENTS_KEY }),
  });
  const today = new Date().toISOString().slice(0, 10);
  return (
    <Stack gap={4}>
      <Text size="xs" c="dimmed">
        {t("investments.periodsHint")}
      </Text>
      <Table fz="xs" verticalSpacing={2}>
        <Table.Tbody>
          {(periods.data ?? []).map((p) => (
            <Table.Tr key={p.number} fw={p.start <= today && today < p.end ? 700 : undefined}>
              <Table.Td>{p.number}</Table.Td>
              <Table.Td>
                {fmtDate(p.start)} – {fmtDate(p.end)}
              </Table.Td>
              <Table.Td>{p.rate != null ? `${Number(p.rate).toFixed(2)}%` : "?"}</Table.Td>
              <Table.Td c="dimmed">
                {t(`investments.rateSource.${p.source}`, {
                  inflation: p.inflation ? (Number(p.inflation) - 100).toFixed(1) : "",
                })}
              </Table.Td>
              <Table.Td w={130}>
                {canEdit && (
                  <NumberInput
                    size="xs"
                    placeholder={t("investments.override")}
                    decimalScale={3}
                    decimalSeparator=","
                    min={0}
                    defaultValue={p.source === "override" ? Number(p.rate) : undefined}
                    onBlur={(e) => {
                      const raw = e.currentTarget.value.replace(",", ".").trim();
                      if (raw === "" && p.source !== "override") return;
                      override.mutate({ period: p.number, rate: raw === "" ? null : raw });
                    }}
                  />
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}
