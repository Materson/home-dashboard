/**
 * Investment forms: an asset (with its first purchase when new), another
 * purchase, a sale, a value entered by hand, and GUS inflation.
 */
import { useEffect, useState } from "react";
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
import { isoDate, parseIsoDate } from "@/lib/format";

import {
  type Asset,
  type AssetInput,
  type AssetKind,
  INVESTMENTS_KEY,
  investmentsApi,
  type Lot,
  type Unit,
} from "./api";

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
  const [first, setFirst] = useState({ bought_on: today(), quantity: "", price_total: "" });

  useEffect(() => {
    if (props.asset === null) return;
    setForm(editing ? { ...editing } : blankAsset);
    setFirst({ bought_on: today(), quantity: "", price_total: "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset on open
  }, [props.asset]);

  const set = <K extends keyof AssetInput>(k: K, v: AssetInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const setKind = (kind: AssetKind) =>
    setForm((f) => ({ ...f, kind, unit: METALS.has(kind) ? "oz" : "pcs", symbol: kind === "crypto" || kind === "stock" ? f.symbol : "" }));
  const isBond = form.kind === "bond";
  const withInterest = form.kind === "other" && !!form.rate;
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
      const purchase = withInterest ? { ...first, quantity: "1" } : first;
      if (!editing && isPositiveAmount(purchase.quantity) && purchase.price_total !== "") {
        await investmentsApi.addLot(saved.id, purchase);
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
    (editing || withInterest || !first.quantity || (isPositiveAmount(first.quantity) && first.price_total !== ""));

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
                    price_total: isBond && v && (!f.price_total || f.price_total === String(Number(f.quantity) * 100)) ? String(Number(v) * 100) : f.price_total,
                  }))
                }
              />
              )}
              <AmountInput
                label={t(withInterest ? "investments.f.deposited" : "investments.f.paid")}
                value={first.price_total}
                onChange={(v) => setFirst((f) => ({ ...f, price_total: v, quantity: withInterest ? "1" : f.quantity }))}
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
  const [form, setForm] = useState({ bought_on: today(), quantity: "", price_total: "" });
  useEffect(() => {
    if (!props.opened) return;
    setForm(
      props.lot
        ? { bought_on: props.lot.bought_on, quantity: props.lot.quantity, price_total: props.lot.price_total }
        : { bought_on: today(), quantity: "", price_total: "" },
    );
  }, [props.opened, props.lot]);
  const save = useMutation({
    mutationFn: () => (props.lot ? investmentsApi.updateLot(props.lot.id, form) : investmentsApi.addLot(props.asset!.id, form)),
    onSuccess: () => {
      refresh();
      props.onClose();
    },
  });
  const unit = props.asset?.kind === "bond" ? "bonds" : `quantity.${props.asset?.unit ?? "pcs"}`;
  const withInterest = props.asset?.kind === "other" && props.asset.rate != null;
  return (
    <Modal opened={props.opened} onClose={props.onClose} title={t(props.lot ? "investments.editLot" : "investments.addLot")}>
      <Stack>
        <DateField label={t("investments.f.boughtOn")} value={form.bought_on} onChange={(v) => setForm((f) => ({ ...f, bought_on: v ?? today() }))} />
        {!withInterest && (
          <AmountInput label={t(`investments.f.${unit}`)} decimalScale={8} value={form.quantity} onChange={(v) => setForm((f) => ({ ...f, quantity: v }))} />
        )}
        <AmountInput
          label={t(withInterest ? "investments.f.deposited" : "investments.f.paid")}
          value={form.price_total}
          onChange={(v) => setForm((f) => ({ ...f, price_total: v, quantity: withInterest ? "1" : f.quantity }))}
        />
        {save.isError && <Alert color="red">{(save.error as Error).message}</Alert>}
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!isPositiveAmount(form.quantity) || form.price_total === ""}>
          {t("finance.action.save")}
        </Button>
      </Stack>
    </Modal>
  );
}

export function SellModal(props: { lot: Lot | null; onClose: () => void }) {
  const { t } = useTranslation();
  const refresh = useRefresh();
  const [form, setForm] = useState({ sold_on: today(), sold_amount: "" });
  useEffect(() => setForm({ sold_on: today(), sold_amount: "" }), [props.lot]);
  const sell = useMutation({
    mutationFn: () => investmentsApi.sellLot(props.lot!.id, form),
    onSuccess: () => {
      refresh();
      props.onClose();
    },
  });
  return (
    <Modal opened={!!props.lot} onClose={props.onClose} title={t("investments.sell")}>
      <Stack>
        <DateField label={t("investments.f.soldOn")} value={form.sold_on} onChange={(v) => setForm((f) => ({ ...f, sold_on: v ?? today() }))} />
        <AmountInput label={t("investments.f.received")} value={form.sold_amount} onChange={(v) => setForm((f) => ({ ...f, sold_amount: v }))} />
        {sell.isError && <Alert color="red">{(sell.error as Error).message}</Alert>}
        <Button onClick={() => sell.mutate()} loading={sell.isPending} disabled={form.sold_amount === ""}>
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
