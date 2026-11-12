/**
 * Investment forms: an asset (with its first purchase when new), another
 * purchase, a sale, a value entered by hand, and GUS inflation.
 */
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Autocomplete,
  Badge,
  Button,
  Group,
  Modal,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { AmountInput, isPositiveAmount } from "@/components/AmountInput";
import { fmtDate, fmtMoney, fmtNumber, fmtQty, isoDate, parseIsoDate } from "@/lib/format";

import {
  type Asset,
  type AssetInput,
  type AssetKind,
  INVESTMENTS_KEY,
  investmentsApi,
  type Lot,
  type LotInput,
  type SaleMoney,
  type TradeCurrency,
  type Unit,
} from "./api";
import { heldLots, heldQuantity, saleCost } from "./selling";

const KINDS: AssetKind[] = ["gold", "silver", "crypto", "stock", "bond", "other"];
const METALS = new Set<AssetKind>(["gold", "silver"]);
type Access = "none" | "view" | "edit";
const COINS = ["bitcoin", "ethereum", "solana", "ripple", "cardano", "dogecoin", "litecoin", "polkadot", "tether"];
const BOND_TYPES = ["EDO", "COI", "ROS", "ROD", "TOS", "OTS", "ROR", "DOR"];
const NEEDS_MARGIN = new Set(["EDO", "COI", "ROS", "ROD", "DOR"]);
const today = () => isoDate(new Date());

function useRefresh() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: INVESTMENTS_KEY });
    qc.invalidateQueries({ queryKey: ["finance"] });
    // Prices download in the background after a save; look again shortly.
    for (const ms of [6000, 20000]) {
      setTimeout(() => qc.invalidateQueries({ queryKey: INVESTMENTS_KEY }), ms);
    }
  };
}

// ---------------- amounts in another currency ----------------

const TRADE_CURRENCIES: TradeCurrency[] = ["PLN", "USD", "EUR", "GBP", "CHF"];

/** An amount paid or received: in PLN, or in another currency with its PLN
 *  rate (``autoRate``: follows NBP's for the date until typed over). */
type Price = { currency: TradeCurrency; amount: string; rate: string; autoRate: boolean };
const plnPrice = (amount = ""): Price => ({ currency: "PLN", amount, rate: "", autoRate: true });
const storedPrice = (currency: TradeCurrency, pln: string, foreign: string | null, rate: string | null): Price =>
  currency === "PLN" || foreign == null ? plnPrice(pln) : { currency, amount: foreign, rate: rate ?? "", autoRate: false };

/** In PLN (null until there's an amount, and a rate for another currency). */
function priceInPln(p: Price): number | null {
  if (p.amount === "") return null;
  if (p.currency === "PLN") return Number(p.amount);
  return p.rate ? Math.round(Number(p.amount) * Number(p.rate) * 100) / 100 : null;
}

const purchaseFields = (p: Price): Omit<LotInput, "bought_on" | "quantity"> =>
  p.currency === "PLN"
    ? { price_currency: "PLN", price_total: p.amount, price_foreign: null, price_rate: null }
    : { price_currency: p.currency, price_foreign: p.amount, price_rate: p.rate || null };

const saleFields = (p: Price): SaleMoney =>
  p.currency === "PLN"
    ? { sold_currency: "PLN", sold_amount: p.amount }
    : { sold_currency: p.currency, sold_foreign: p.amount, sold_rate: p.rate || null };

/** What was paid / received, in PLN or another currency. Another currency is
 *  converted at NBP's average rate from the last working day before ``day``
 *  (as for tax) — or at the rate typed in (e.g. the broker's). */
function PriceInput(props: { label: string; day: string; value: Price; onChange: (p: Price) => void; foreign?: boolean }) {
  const { t } = useTranslation();
  const { value: p, onChange } = props;
  const other = p.currency !== "PLN";
  const nbp = useQuery({
    queryKey: ["investments-fx-rate", p.currency, props.day],
    queryFn: () => investmentsApi.fxRate(p.currency, props.day),
    enabled: other && !!props.day,
    staleTime: Infinity,
    retry: 1,
  });
  const found = nbp.data && nbp.data.currency === p.currency && nbp.data.on === props.day ? nbp.data : null;
  // Another date: follow NBP's rate for it again.
  const lastDay = useRef(props.day);
  useEffect(() => {
    if (lastDay.current === props.day) return;
    lastDay.current = props.day;
    if (other && !p.autoRate) onChange({ ...p, autoRate: true });
  });
  useEffect(() => {
    if (other && p.autoRate && found && found.rate !== p.rate) onChange({ ...p, rate: found.rate });
  });
  const pln = priceInPln(p);
  const nbpNote = !found
    ? undefined
    : p.autoRate || Number(p.rate) === Number(found.rate)
      ? t("investments.fxRateNbp", { date: fmtDate(found.rate_date) })
      : t("investments.fxRateOwn", { date: fmtDate(found.rate_date), rate: fmtNumber(found.rate, 4) });
  return (
    <Stack gap={6}>
      <Group gap="xs" align="flex-end" wrap="nowrap">
        <AmountInput label={props.label} value={p.amount} onChange={(v) => onChange({ ...p, amount: v })} style={{ flex: 1 }} />
        {props.foreign !== false && (
          <Select
            w={88}
            aria-label={t("investments.currency")}
            allowDeselect={false}
            data={TRADE_CURRENCIES}
            value={p.currency}
            onChange={(v) => onChange({ ...p, currency: (v ?? "PLN") as TradeCurrency, rate: "", autoRate: true })}
          />
        )}
      </Group>
      {other && (
        <>
          <AmountInput
            label={t("investments.f.fxRate", { currency: p.currency })}
            description={nbp.isError ? t("investments.fxRateError") : nbpNote}
            decimalScale={6}
            value={p.rate}
            onChange={(v) => onChange({ ...p, rate: v, autoRate: false })}
          />
          <Text size="xs" c="dimmed">
            {t("investments.inPln", { amount: pln != null ? fmtMoney(pln.toFixed(2)) : "—" })}
          </Text>
        </>
      )}
    </Stack>
  );
}

function DateField(props: { label: string; value: string | null; onChange: (v: string | null) => void; clearable?: boolean }) {
  return (
    <DatePickerInput
      label={props.label}
      clearable={props.clearable}
      maxDate={new Date()}
      value={props.value ? parseIsoDate(props.value) : null}
      onChange={(d) => props.onChange(d ? isoDate(d) : null)}
    />
  );
}

// ---------------- asset ----------------

const blankAsset: AssetInput = {
  name: "",
  kind: "gold",
  unit: "oz",
  symbol: "",
  person_id: null,
  bond_type: "EDO",
  bond_first_rate: null,
  bond_margin: null,
  rate: null,
  compounding: "none",
  term_months: null,
  notes: "",
};
const COMPOUNDINGS = ["none", "monthly", "quarterly", "yearly"] as const;

export function AssetModal(props: { asset: Asset | null | "new"; onClose: () => void }) {
  const { t } = useTranslation();
  const refresh = useRefresh();
  const editing = props.asset && props.asset !== "new" ? props.asset : null;
  const [form, setForm] = useState<AssetInput>(blankAsset);
  const [first, setFirst] = useState({ bought_on: today(), quantity: "", price: plnPrice() });

  useEffect(() => {
    if (props.asset === null) return;
    setForm(editing ? { ...editing } : blankAsset);
    setFirst({ bought_on: today(), quantity: "", price: plnPrice() });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset on open
  }, [props.asset]);

  const set = <K extends keyof AssetInput>(k: K, v: AssetInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const setKind = (kind: AssetKind) =>
    setForm((f) => ({ ...f, kind, unit: METALS.has(kind) ? "oz" : "pcs", symbol: kind === "crypto" || kind === "stock" ? f.symbol : "" }));
  const isBond = form.kind === "bond";
  const withInterest = form.kind === "other" && !!form.rate;
  // Bonds and deposits are in PLN; the rest may be bought in another currency.
  const foreignOk = !isBond && !withInterest;
  const isOwner = !editing || editing.is_owner;
  const people = useQuery({ queryKey: [...INVESTMENTS_KEY, "people"], queryFn: investmentsApi.people, enabled: props.asset !== null });
  const [access, setAccess] = useState<Record<number, Access>>({});
  useEffect(() => {
    if (props.asset === null) return;
    setAccess(Object.fromEntries((editing?.shares ?? []).map((s) => [s.user_id, s.can_edit ? "edit" : "view"])));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset on open
  }, [props.asset]);

  const save = useMutation({
    mutationFn: async () => {
      const body = { ...form, name: form.name || (isBond ? form.bond_type : "") };
      const saved = await investmentsApi.saveAsset(body, editing?.id);
      if (isOwner) {
        const shares = Object.entries(access)
          .filter(([, a]) => a !== "none")
          .map(([id, a]) => ({ user_id: Number(id), can_edit: a === "edit" }));
        if (shares.length || editing?.shares.length) await investmentsApi.setShares(saved.id, shares);
      }
      const quantity = withInterest ? "1" : first.quantity;
      if (!editing && isPositiveAmount(quantity) && first.price.amount !== "") {
        const price: Price = foreignOk ? first.price : { ...first.price, currency: "PLN" };
        await investmentsApi.addLot(saved.id, { bought_on: first.bought_on, quantity, ...purchaseFields(price) });
      }
      return saved;
    },
    onSuccess: () => {
      refresh();
      props.onClose();
    },
  });

  const valid =
    (form.name.trim() || isBond) &&
    (form.kind !== "crypto" || form.symbol.trim()) &&
    (!isBond || (form.bond_first_rate && (!NEEDS_MARGIN.has(form.bond_type) || form.bond_margin))) &&
    (editing || withInterest || !first.quantity || (isPositiveAmount(first.quantity) && first.price.amount !== ""));

  return (
    <Modal opened={props.asset !== null} onClose={props.onClose} title={t(editing ? "investments.edit" : "investments.add")} size="lg">
      <Stack>
        {!editing && (
          <SegmentedControl
            value={form.kind}
            onChange={(v) => setKind(v as AssetKind)}
            data={KINDS.map((k) => ({ value: k, label: t(`investments.kind.${k}`) }))}
          />
        )}
        <Text size="xs" c="dimmed">
          {t(`investments.kindHint.${form.kind}`)}
        </Text>
        {isBond ? (
          <>
            <Group grow align="flex-start">
              <Select
                label={t("investments.f.bondType")}
                allowDeselect={false}
                data={BOND_TYPES.map((b) => ({ value: b, label: `${b} — ${t(`investments.bond.${b}`)}` }))}
                value={form.bond_type}
                onChange={(v) => set("bond_type", v ?? "EDO")}
              />
              <TextInput
                label={t("investments.f.series")}
                placeholder={`${form.bond_type}1136`}
                value={form.name}
                onChange={(e) => set("name", e.currentTarget.value.toUpperCase())}
              />
            </Group>
            <Group grow align="flex-start">
              <AmountInput
                label={t("investments.f.firstRate")}
                description={t("investments.f.firstRateHint")}
                decimalScale={3}
                value={form.bond_first_rate ?? ""}
                onChange={(v) => set("bond_first_rate", v || null)}
              />
              {NEEDS_MARGIN.has(form.bond_type) && (
                <AmountInput
                  label={t("investments.f.margin")}
                  description={t(form.bond_type === "DOR" ? "investments.f.marginNbp" : "investments.f.marginCpi")}
                  decimalScale={3}
                  value={form.bond_margin ?? ""}
                  onChange={(v) => set("bond_margin", v || null)}
                />
              )}
            </Group>
          </>
        ) : (
          <TextInput
            label={t("investments.f.name")}
            placeholder={t(`investments.namePlaceholder.${form.kind}`)}
            required
            value={form.name}
            onChange={(e) => set("name", e.currentTarget.value)}
          />
        )}
        {METALS.has(form.kind) && (
          <Select
            label={t("investments.f.unit")}
            description={t("investments.f.metalUnitHint")}
            allowDeselect={false}
            data={(["oz", "g"] as Unit[]).map((u) => ({ value: u, label: t(`investments.unit.${u}`) }))}
            value={form.unit}
            onChange={(v) => set("unit", (v ?? "oz") as Unit)}
          />
        )}
        {form.kind === "crypto" && (
          <Autocomplete
            label={t("investments.f.coin")}
            description={t("investments.f.coinHint")}
            required
            data={COINS}
            value={form.symbol}
            onChange={(v) => set("symbol", v)}
          />
        )}
        {form.kind === "other" && (
          <Stack gap={6}>
            <Group grow align="flex-start">
              <AmountInput
                label={t("investments.f.rate")}
                description={t("investments.f.rateHint")}
                decimalScale={3}
                value={form.rate ?? ""}
                onChange={(v) => set("rate", v || null)}
              />
              <Select
                label={t("investments.f.compounding")}
                allowDeselect={false}
                disabled={!form.rate}
                data={COMPOUNDINGS.map((c) => ({ value: c, label: t(`investments.compounding.${c}`) }))}
                value={form.compounding}
                onChange={(v) => set("compounding", (v ?? "none") as AssetInput["compounding"])}
              />
              <NumberInput
                label={t("investments.f.term")}
                description={t("investments.f.termHint")}
                disabled={!form.rate}
                min={1}
                max={600}
                value={form.term_months ?? ""}
                onChange={(v) => set("term_months", v === "" ? null : Number(v))}
              />
            </Group>
          </Stack>
        )}
        {form.kind === "stock" && (
          <TextInput
            label={t("investments.f.ticker")}
            description={t("investments.f.tickerHint")}
            placeholder="CSPX.L"
            value={form.symbol}
            onChange={(e) => set("symbol", e.currentTarget.value.toUpperCase())}
          />
        )}

        {!editing && (
          <>
            <Text fw={600} size="sm" mt="xs">
              {t("investments.firstPurchase")}
            </Text>
            <Group grow align="flex-start">
              <DateField label={t("investments.f.boughtOn")} value={first.bought_on} onChange={(v) => setFirst((f) => ({ ...f, bought_on: v ?? today() }))} />
              {!withInterest && (
              <AmountInput
                label={t(isBond ? "investments.f.bonds" : `investments.f.quantity.${form.unit}`)}
                decimalScale={8}
                value={first.quantity}
                onChange={(v) =>
                  setFirst((f) => ({
                    ...f,
                    quantity: v,
                    // A bond costs 100 zł unless it was bought for less (e.g. an exchange).
                    price:
                      isBond && v && (!f.price.amount || f.price.amount === String(Number(f.quantity) * 100))
                        ? plnPrice(String(Number(v) * 100))
                        : f.price,
                  }))
                }
              />
              )}
              <PriceInput
                label={t(withInterest ? "investments.f.deposited" : foreignOk ? "investments.f.paidIn" : "investments.f.paid")}
                day={first.bought_on}
                foreign={foreignOk}
                value={first.price}
                onChange={(price) => setFirst((f) => ({ ...f, price, quantity: withInterest ? "1" : f.quantity }))}
              />
            </Group>
          </>
        )}
        {isOwner && (people.data?.length ?? 0) > 0 && (
          <Stack gap={6}>
            <Text fw={600} size="sm" mt="xs">
              {t("investments.sharing")}
            </Text>
            <Text size="xs" c="dimmed">
              {t("investments.sharingHint")}
            </Text>
            {(people.data ?? []).map((p) => (
              <Group key={p.user_id} justify="space-between">
                <Text size="sm">{p.name}</Text>
                <SegmentedControl
                  size="xs"
                  value={access[p.user_id] ?? "none"}
                  onChange={(v) => setAccess((a) => ({ ...a, [p.user_id]: v as Access }))}
                  data={[
                    { value: "none", label: t("notes.access.none") },
                    { value: "view", label: t("notes.access.view") },
                    { value: "edit", label: t("notes.access.edit") },
                  ]}
                />
              </Group>
            ))}
          </Stack>
        )}
        {save.isError && <Alert color="red">{(save.error as Error).message}</Alert>}
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!valid}>
          {t("finance.action.save")}
        </Button>
      </Stack>
    </Modal>
  );
}

// ---------------- purchase / sale / value ----------------

export function LotModal(props: { asset: Asset | null; lot: Lot | null; opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const refresh = useRefresh();
  const [form, setForm] = useState({ bought_on: today(), quantity: "", price: plnPrice() });
  useEffect(() => {
    if (!props.opened) return;
    const lot = props.lot;
    setForm(
      lot
        ? {
            bought_on: lot.bought_on,
            quantity: lot.quantity,
            price: storedPrice(lot.price_currency, lot.price_total, lot.price_foreign, lot.price_rate),
          }
        : { bought_on: today(), quantity: "", price: plnPrice() },
    );
  }, [props.opened, props.lot]);
  const unit = props.asset?.kind === "bond" ? "bonds" : `quantity.${props.asset?.unit ?? "pcs"}`;
  const withInterest = props.asset?.kind === "other" && props.asset.rate != null;
  const foreignOk = props.asset?.kind !== "bond" && !withInterest;
  const save = useMutation({
    mutationFn: () => {
      const body: LotInput = {
        bought_on: form.bought_on,
        quantity: withInterest ? "1" : form.quantity,
        ...purchaseFields(foreignOk ? form.price : { ...form.price, currency: "PLN" }),
      };
      return props.lot ? investmentsApi.updateLot(props.lot.id, body) : investmentsApi.addLot(props.asset!.id, body);
    },
    onSuccess: () => {
      refresh();
      props.onClose();
    },
  });
  return (
    <Modal opened={props.opened} onClose={props.onClose} title={t(props.lot ? "investments.editLot" : "investments.addLot")}>
      <Stack>
        <DateField label={t("investments.f.boughtOn")} value={form.bought_on} onChange={(v) => setForm((f) => ({ ...f, bought_on: v ?? today() }))} />
        {!withInterest && (
          <AmountInput label={t(`investments.f.${unit}`)} decimalScale={8} value={form.quantity} onChange={(v) => setForm((f) => ({ ...f, quantity: v }))} />
        )}
        <PriceInput
          label={t(withInterest ? "investments.f.deposited" : foreignOk ? "investments.f.paidIn" : "investments.f.paid")}
          day={form.bought_on}
          foreign={foreignOk}
          value={form.price}
          onChange={(price) => setForm((f) => ({ ...f, price }))}
        />
        {save.isError && <Alert color="red">{(save.error as Error).message}</Alert>}
        <Button
          onClick={() => save.mutate()}
          loading={save.isPending}
          disabled={(!withInterest && !isPositiveAmount(form.quantity)) || form.price.amount === ""}
        >
          {t("finance.action.save")}
        </Button>
      </Stack>
    </Modal>
  );
}

/** A sale: of one purchase (``lot``; all of it or a part), or — with no
 *  ``lot`` — part of the whole holding, oldest purchases first. A sold part
 *  becomes its own purchase row with its share of the price. */
export function SellModal(props: { asset: Asset | null; lot: Lot | null; opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const refresh = useRefresh();
  const { asset, lot } = props;
  // A deposit is one sum (quantity 1): it's closed whole. Both are in PLN.
  const deposit = asset?.kind === "other" && asset.rate != null;
  const bond = asset?.kind === "bond";
  const blank = () => ({ sold_on: today(), quantity: lot ? lot.quantity : "", received: plnPrice() });
  const [form, setForm] = useState(blank);
  useEffect(() => {
    if (props.opened) setForm(blank());
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset on open
  }, [props.opened, lot]);
  const from = lot ? [lot] : heldLots(asset?.lots ?? [], form.sold_on);
  const max = heldQuantity(from);
  const qty = Number(form.quantity);
  const qtyOk = isPositiveAmount(form.quantity) && qty <= max + 1e-9 && (!bond || Number.isInteger(qty));
  const cost = qtyOk ? saleCost(from, qty) : null;
  const received = priceInPln(form.received);
  const sell = useMutation({
    mutationFn: (): Promise<Lot | Lot[]> => {
      const money = saleFields(deposit || bond ? { ...form.received, currency: "PLN" } : form.received);
      return lot
        ? investmentsApi.sellLot(lot.id, { sold_on: form.sold_on, ...money, ...(deposit ? {} : { quantity: form.quantity }) })
        : investmentsApi.sellAsset(asset!.id, { sold_on: form.sold_on, quantity: form.quantity, ...money });
    },
    onSuccess: () => {
      refresh();
      props.onClose();
    },
  });
  const unit = bond ? "bonds" : `quantity.${asset?.unit ?? "pcs"}`;
  return (
    <Modal opened={props.opened && !!asset} onClose={props.onClose} title={t("investments.sell")}>
      <Stack>
        <Text size="sm" c="dimmed">
          {t(lot ? "investments.sellLotHint" : "investments.sellFifoHint")}
        </Text>
        <DateField label={t("investments.f.soldOn")} value={form.sold_on} onChange={(v) => setForm((f) => ({ ...f, sold_on: v ?? today() }))} />
        {!deposit && (
          <AmountInput
            label={t(`investments.f.${unit}`)}
            description={t("investments.sellOf", { max: fmtQty(max) })}
            decimalScale={bond ? 0 : 8}
            value={form.quantity}
            onChange={(v) => setForm((f) => ({ ...f, quantity: v }))}
            error={form.quantity !== "" && !qtyOk ? t(bond ? "investments.sellWholeBonds" : "investments.sellTooMuch") : undefined}
            rightSectionWidth={80}
            rightSection={
              <Button size="compact-xs" variant="subtle" onClick={() => setForm((f) => ({ ...f, quantity: String(Number(max.toFixed(8))) }))}>
                {t("investments.sellAll")}
              </Button>
            }
          />
        )}
        <PriceInput
          label={t(deposit || bond ? "investments.f.received" : "investments.f.receivedIn")}
          day={form.sold_on}
          foreign={!deposit && !bond}
          value={form.received}
          onChange={(v) => setForm((f) => ({ ...f, received: v }))}
        />
        {cost != null && received != null && (
          <Text size="sm">
            {t("investments.sellPreview", {
              cost: fmtMoney(cost.toFixed(2)),
              gain: fmtMoney((received - cost).toFixed(2)),
            })}
          </Text>
        )}
        {sell.isError && <Alert color="red">{(sell.error as Error).message}</Alert>}
        <Button onClick={() => sell.mutate()} loading={sell.isPending} disabled={form.received.amount === "" || (!deposit && !qtyOk)}>
          {t("investments.sell")}
        </Button>
      </Stack>
    </Modal>
  );
}

export function ValueModal(props: { asset: Asset | null; onClose: () => void }) {
  const { t } = useTranslation();
  const refresh = useRefresh();
  const [mode, setMode] = useState<"total" | "unit">("total");
  const [on, setOn] = useState(today());
  const [amount, setAmount] = useState("");
  useEffect(() => setAmount(""), [props.asset]);
  const save = useMutation({
    mutationFn: () =>
      investmentsApi.setValue(props.asset!.id, mode === "total" ? { on, total: amount } : { on, unit_price: amount }),
    onSuccess: () => {
      refresh();
      props.onClose();
    },
  });
  return (
    <Modal opened={!!props.asset} onClose={props.onClose} title={t("investments.setValue")}>
      <Stack>
        <Text size="sm" c="dimmed">
          {t("investments.setValueHint")}
        </Text>
        <SegmentedControl
          value={mode}
          onChange={(v) => setMode(v as "total" | "unit")}
          data={[
            { value: "total", label: t("investments.valueTotal") },
            { value: "unit", label: t("investments.valueUnit") },
          ]}
        />
        <DateField label={t("investments.f.date")} value={on} onChange={(v) => setOn(v ?? today())} />
        <AmountInput label={t(mode === "total" ? "investments.valueTotal" : "investments.valueUnit")} decimalScale={6} value={amount} onChange={setAmount} />
        {save.isError && <Alert color="red">{(save.error as Error).message}</Alert>}
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!isPositiveAmount(amount)}>
          {t("finance.action.save")}
        </Button>
      </Stack>
    </Modal>
  );
}

// ---------------- inflation ----------------

export function InflationModal(props: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const rows = useQuery({ queryKey: [...INVESTMENTS_KEY, "inflation"], queryFn: investmentsApi.inflation, enabled: props.opened });
  const now = new Date();
  const [year, setYear] = useState<number>(now.getFullYear());
  const [month, setMonth] = useState<number>(now.getMonth() || 12);
  const [index, setIndex] = useState("");
  const add = useMutation({
    mutationFn: () => investmentsApi.addInflation({ year, month, index }),
    onSuccess: () => {
      setIndex("");
      qc.invalidateQueries({ queryKey: INVESTMENTS_KEY });
    },
  });
  return (
    <Modal opened={props.opened} onClose={props.onClose} title={t("investments.inflation.title")} size="md">
      <Stack>
        <Text size="sm" c="dimmed">
          {t("investments.inflation.hint")}
        </Text>
        <Table fz="sm" verticalSpacing={2}>
          <Table.Tbody>
            {(rows.data ?? []).map((r) => (
              <Table.Tr key={`${r.year}-${r.month}`}>
                <Table.Td>{`${r.year}-${String(r.month).padStart(2, "0")}`}</Table.Td>
                <Table.Td>{r.index}</Table.Td>
                <Table.Td c="dimmed">{t("investments.inflation.percent", { value: (Number(r.index) - 100).toFixed(1) })}</Table.Td>
                <Table.Td>
                  {r.manual && (
                    <Badge size="xs" variant="light">
                      {t("investments.inflation.manual")}
                    </Badge>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {rows.isSuccess && !rows.data.length && (
          <Text size="sm" c="dimmed">
            {t("investments.inflation.none")}
          </Text>
        )}
        <Group align="flex-end" grow>
          <NumberInput label={t("investments.inflation.year")} value={year} onChange={(v) => setYear(Number(v))} min={2000} max={2100} />
          <NumberInput label={t("investments.inflation.month")} value={month} onChange={(v) => setMonth(Number(v))} min={1} max={12} />
          <AmountInput label={t("investments.inflation.index")} placeholder="104,1" value={index} onChange={setIndex} />
        </Group>
        {add.isError && <Alert color="red">{(add.error as Error).message}</Alert>}
        <Button variant="light" onClick={() => add.mutate()} loading={add.isPending} disabled={!isPositiveAmount(index)}>
          {t("investments.inflation.add")}
        </Button>
      </Stack>
    </Modal>
  );
}
