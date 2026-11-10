/**
 * Table + add/edit/delete form for one car record type, driven entirely by
 * the field definitions in `records.ts`.
 */
import { useEffect, useState } from "react";
import {
  ActionIcon,
  Button,
  Checkbox,
  Group,
  Modal,
  NumberInput,
  Popover,
  ScrollArea,
  Select,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { AmountInput, isPositiveAmount } from "@/components/AmountInput";
import { fmtDate, fmtMoney, fmtNumber, isoDate, parseIsoDate } from "@/lib/format";

import { carsApi, type CarRecord, type RecordKind } from "./api";
import { applyEdit, RECORDS, type FieldDef } from "./records";

type FormValue = string | boolean;
type FormState = Record<string, FormValue>;

export function RecordSection({ carId, kind }: { carId: string; kind: RecordKind }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const fields = RECORDS[kind];
  const [editing, setEditing] = useState<CarRecord | null | "new">(null);

  const records = useQuery({
    queryKey: ["cars", carId, kind],
    queryFn: () => carsApi.records(carId, kind),
  });
  const remove = useMutation({
    mutationFn: (id: string) => carsApi.deleteRecord(carId, kind, id),
    // Any record can move the odometer, costs or reminders: refresh the car.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cars", carId] }),
  });

  const columns = fields.filter((f) => f.column);

  return (
    <Stack gap="sm">
      <Group justify="flex-end">
        <Button size="xs" leftSection={<IconPlus size={14} />} onClick={() => setEditing("new")}>
          {t("cars.addRecord")}
        </Button>
      </Group>
      <ScrollArea>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              {columns.map((f) => (
                <Table.Th key={f.name} ta={isNumeric(f) ? "right" : undefined}>
                  {t(f.labelKey)}
                </Table.Th>
              ))}
              {kind === "fuel" && <Table.Th ta="right">{t("cars.f.effectivePrice")}</Table.Th>}
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(records.data ?? []).map((r) => (
              <Table.Tr key={r.id}>
                {columns.map((f) => (
                  <Table.Td key={f.name} ta={isNumeric(f) ? "right" : undefined}>
                    {display(f, r, t)}
                  </Table.Td>
                ))}
                {kind === "fuel" && (
                  <Table.Td ta="right">{fmtNumber(r.effective_price_per_litre as string, 2)}</Table.Td>
                )}
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    <Tooltip label={t("finance.action.edit")}>
                      <ActionIcon variant="subtle" onClick={() => setEditing(r)}>
                        <IconPencil size={16} />
                      </ActionIcon>
                    </Tooltip>
                    <Popover withArrow>
                      <Popover.Target>
                        <ActionIcon variant="subtle" color="red" aria-label={t("finance.action.delete")}>
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Popover.Target>
                      <Popover.Dropdown>
                        <Stack gap="xs">
                          <Text size="sm">{t("cars.deleteConfirm")}</Text>
                          <Button size="xs" color="red" onClick={() => remove.mutate(r.id)}>
                            {t("finance.action.delete")}
                          </Button>
                        </Stack>
                      </Popover.Dropdown>
                    </Popover>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
            {records.isSuccess && !records.data.length && (
              <Table.Tr>
                <Table.Td colSpan={columns.length + 2} ta="center" c="dimmed" py="md">
                  {t("cars.noRecords")}
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      <RecordModal
        carId={carId}
        kind={kind}
        record={editing === "new" ? null : editing}
        opened={editing !== null}
        onClose={() => setEditing(null)}
      />
    </Stack>
  );
}

function isNumeric(f: FieldDef) {
  return f.type === "int" || f.type === "amount";
}

function display(f: FieldDef, r: CarRecord, t: (k: string) => string): string {
  const v = r[f.name];
  if (v === null || v === undefined || v === "") return "—";
  switch (f.type) {
    case "date":
      return fmtDate(v as string);
    case "int":
      return fmtNumber(v as number);
    case "amount":
      return f.currencyField
        ? fmtMoney(v as string, r[f.currencyField] as string)
        : fmtNumber(v as string, 2); // tables always show 2 decimals; `scale` only widens input
    case "bool":
      return v ? "✓" : "—";
    case "select":
      return t(`${f.optionsKey}.${v}`);
    default:
      return String(v);
  }
}

// ---- form ----------------------------------------------------------------

function initialState(fields: FieldDef[], record: CarRecord | null): FormState {
  const state: FormState = {};
  for (const f of fields) {
    const v = record?.[f.name];
    if (record) {
      state[f.name] = f.type === "bool" ? Boolean(v) : v === null || v === undefined ? "" : String(v);
    } else if (f.default !== undefined) {
      state[f.name] = f.default;
    } else if (f.type === "date" && f.required) {
      state[f.name] = isoDate(new Date());
    } else if (f.type === "select") {
      state[f.name] = f.options?.[0] ?? "";
    } else {
      state[f.name] = f.type === "bool" ? false : "";
    }
  }
  if (!record) {
    // New entry: pre-fill derived fields from the defaults (e.g. valid until
    // = today + 1 year), but only those derived when nothing is hand-typed.
    for (const f of fields) {
      if (!f.compute || (f.compute.active && !f.compute.active(new Set()))) continue;
      const computed = f.compute.fn(state);
      if (computed) state[f.name] = computed;
    }
  }
  return state;
}

/** Form state → API payload: empty optional values become null. */
function toPayload(fields: FieldDef[], state: FormState): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) {
    const v = state[f.name];
    if (f.type === "bool") out[f.name] = Boolean(v);
    else if (v === "" || v === undefined) out[f.name] = f.type === "text" || f.type === "textarea" ? "" : null;
    else if (f.type === "int") out[f.name] = Math.round(Number(v));
    else out[f.name] = v;
  }
  return out;
}

function isValid(fields: FieldDef[], state: FormState): boolean {
  return fields.every((f) => {
    if (!f.required) return true;
    const v = state[f.name];
    if (f.type === "amount") return isPositiveAmount(String(v));
    return v !== "" && v !== undefined;
  });
}

export function RecordModal(props: {
  carId: string;
  kind: RecordKind;
  record: CarRecord | null;
  opened: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const fields = RECORDS[props.kind];
  const [state, setState] = useState<FormState>(() => initialState(fields, props.record));
  // Computed fields the user has typed into: stop overwriting those.
  const [manual, setManual] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!props.opened) return;
    const initial = initialState(fields, props.record);
    setState(initial);
    // Editing: a stored value that differs from the calculation was typed by
    // hand (e.g. receipt rounding) — keep it unless the user changes it.
    const handTyped = fields.filter((f) => {
      if (!f.compute || !props.record) return false;
      const computed = f.compute.fn(initial);
      return computed !== null && Number(computed) !== Number(initial[f.name]);
    });
    setManual(new Set(handTyped.map((f) => f.name)));
  }, [props.opened, props.record, fields]);

  const save = useMutation({
    mutationFn: () =>
      carsApi.saveRecord(props.carId, props.kind, toPayload(fields, state), props.record?.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cars", props.carId] });
      qc.invalidateQueries({ queryKey: ["finance"] }); // costs land in the ledger
      props.onClose();
    },
  });

  const set = (name: string, value: FormValue) => {
    const result = applyEdit(fields, state, manual, name, value);
    setManual(result.handTyped);
    setState(result.state);
  };

  return (
    <Modal
      opened={props.opened}
      onClose={props.onClose}
      title={t(props.record ? "cars.editRecord" : "cars.addRecord")}
    >
      <Stack>
        {fields.map((f) => (
          <Field key={f.name} def={f} value={state[f.name]} onChange={(v) => set(f.name, v)} />
        ))}
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!isValid(fields, state)}>
          {t("finance.action.save")}
        </Button>
      </Stack>
    </Modal>
  );
}

function Field({
  def,
  value,
  onChange,
}: {
  def: FieldDef;
  value: FormValue;
  onChange: (v: FormValue) => void;
}) {
  const { t } = useTranslation();
  const common = {
    label: t(def.labelKey),
    required: def.required,
    description: def.hintKey ? t(def.hintKey) : undefined,
  };
  switch (def.type) {
    case "date":
      return (
        <DatePickerInput
          {...common}
          clearable={!def.required}
          value={value ? parseIsoDate(String(value)) : null}
          onChange={(d) => onChange(d ? isoDate(d) : "")}
        />
      );
    case "int":
      return (
        <NumberInput
          {...common}
          allowDecimal={false}
          allowNegative={false}
          hideControls
          thousandSeparator=" "
          value={value === "" ? "" : Number(value)}
          onChange={(v) => onChange(v === "" ? "" : String(v))}
          onFocus={(e) => e.currentTarget.select()}
        />
      );
    case "amount":
      return (
        <AmountInput
          {...common}
          decimalScale={def.scale ?? 2}
          value={String(value)}
          onChange={onChange}
        />
      );
    case "bool":
      return (
        <Checkbox
          label={common.label}
          description={common.description}
          checked={Boolean(value)}
          onChange={(e) => onChange(e.currentTarget.checked)}
        />
      );
    case "select":
      return (
        <Select
          {...common}
          allowDeselect={false}
          data={(def.options ?? []).map((o) => ({ value: o, label: t(`${def.optionsKey}.${o}`) }))}
          value={String(value)}
          onChange={(v) => onChange(v ?? "")}
        />
      );
    case "textarea":
      return (
        <Textarea {...common} autosize minRows={2} value={String(value)} onChange={(e) => onChange(e.currentTarget.value)} />
      );
    default:
      return <TextInput {...common} value={String(value)} onChange={(e) => onChange(e.currentTarget.value)} />;
  }
}
