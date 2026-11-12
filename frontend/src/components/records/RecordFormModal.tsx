/** Add/edit form for one field-driven record (see `fields.ts`). */
import { Fragment, type ReactNode, useEffect, useState } from "react";
import {
  Alert,
  Autocomplete,
  Button,
  Checkbox,
  ColorInput,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  TagsInput,
  Textarea,
  TextInput,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { AmountInput } from "@/components/AmountInput";
import { TimeField } from "@/components/TimeField";
import { isoDate, parseIsoDate } from "@/lib/format";

import {
  applyEdit,
  applyFills,
  handTypedOnLoad,
  initialState,
  isValid,
  normalizeTime,
  toPayload,
  type Choices,
  type FieldDef,
  type Fills,
  type FormState,
  type FormValue,
  type Row,
  type Suggestions,
} from "./fields";

/** Renders extra form content from the current values; `set` changes a field. */
export type FormExtra = (state: FormState, set: (name: string, value: FormValue) => void) => ReactNode;
/** Extra content placed right under the named field, e.g. `{ dosage: calculator }`. */
export type FormExtras = Record<string, FormExtra>;

export function RecordFormModal(props: {
  fields: FieldDef[];
  record: Row | null;
  opened: boolean;
  onClose: () => void;
  /** Persist the payload; extra fields (e.g. person_id) are added by the caller. */
  onSave: (payload: Record<string, unknown>) => Promise<unknown>;
  onSaved?: () => void;
  titleKey: { add: string; edit: string };
  choices?: Choices;
  suggestions?: Suggestions;
  fills?: Fills;
  /** Pre-set values for a new record. */
  defaults?: FormState;
  /** Extra content under a field (e.g. a dose calculator under Dosage); may set fields. */
  extras?: FormExtras;
}) {
  const { t } = useTranslation();
  const { fields } = props;
  const [state, setState] = useState<FormState>(() =>
    initialState(fields, props.record, props.defaults),
  );
  const [handTyped, setHandTyped] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!props.opened) return;
    const initial = initialState(fields, props.record, props.defaults);
    setState(initial);
    setHandTyped(handTypedOnLoad(fields, initial, !!props.record));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- defaults only matter on open
  }, [props.opened, props.record, fields]);

  const save = useMutation({
    mutationFn: () => props.onSave(toPayload(fields, state)),
    onSuccess: () => {
      props.onSaved?.();
      props.onClose();
    },
  });

  const set = (name: string, value: FormValue) => {
    const result = applyEdit(fields, state, handTyped, name, value);
    setHandTyped(result.handTyped);
    setState(applyFills(result.state, props.fills, name, value));
  };

  return (
    <Modal
      opened={props.opened}
      onClose={props.onClose}
      title={t(props.record ? props.titleKey.edit : props.titleKey.add)}
    >
      <Stack>
        {fields.map((f) => (
          <Fragment key={f.name}>
            <Field
              def={f}
              value={state[f.name]}
              choices={props.choices?.[f.name]}
              suggestions={props.suggestions?.[f.suggestKey ?? f.name]}
              onChange={(v) => set(f.name, v)}
            />
            {props.extras?.[f.name]?.(state, set)}
          </Fragment>
        ))}
        {save.isError && <Alert color="red">{t("common.saveFailed")}</Alert>}
        <Button
          onClick={() => save.mutate()}
          loading={save.isPending}
          disabled={!isValid(fields, state)}
        >
          {t("finance.action.save")}
        </Button>
      </Stack>
    </Modal>
  );
}

function Field({
  def,
  value,
  choices,
  suggestions,
  onChange,
}: {
  def: FieldDef;
  value: FormValue;
  choices?: { value: string; label: string }[];
  suggestions?: string[];
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
    case "datetime": {
      // A date picker + our own 24h time field. Mantine's DateTimePicker uses
      // the browser's time input (12h/24h follows the OS, and its changes
      // were not always reported), so the time could stay at 00:00.
      const [datePart = "", timePart = ""] = String(value).split("T");
      const join = (d: string, t: string) => (d || t ? `${d}T${t}` : "");
      return (
        <Group grow align="flex-start">
          <DatePickerInput
            {...common}
            clearable={!def.required}
            value={datePart ? parseIsoDate(datePart) : null}
            onChange={(d) => onChange(join(d ? isoDate(d) : "", timePart))}
          />
          <TimeField
            label={t("common.time")}
            required={def.required}
            value={timePart}
            onChange={(tm) => onChange(join(datePart, tm))}
          />
        </Group>
      );
    }
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
    case "choice":
      return (
        <Select
          {...common}
          clearable={!def.required}
          searchable
          data={choices ?? []}
          value={value ? String(value) : null}
          onChange={(v) => onChange(v ?? "")}
        />
      );
    case "color":
      return (
        <ColorInput
          {...common}
          format="hex"
          swatches={["#4c6ef5", "#e64980", "#12b886", "#fab005", "#fd7e14", "#7950f2", "#868e96"]}
          value={String(value)}
          onChange={onChange}
        />
      );
    case "times":
      return (
        <TagsInput
          {...common}
          placeholder="08:00"
          splitChars={[",", " "]}
          value={String(value) ? String(value).split(/[,\s]+/).filter(Boolean) : []}
          // "8" or "830" become "08:00" / "08:30" as soon as they're added.
          onChange={(tags) => onChange(tags.map((tag) => normalizeTime(tag) ?? tag).join(", "))}
          error={
            String(value)
              .split(/[,\s]+/)
              .filter(Boolean)
              .some((tag) => normalizeTime(tag) === null)
              ? t("common.badTime")
              : undefined
          }
        />
      );
    case "textarea":
      return (
        <Textarea
          {...common}
          autosize
          minRows={2}
          value={String(value)}
          onChange={(e) => onChange(e.currentTarget.value)}
        />
      );
    default:
      if (suggestions?.length) {
        // Free text, with earlier values offered as you type (or on focus).
        return (
          <Autocomplete
            {...common}
            data={suggestions}
            limit={8}
            value={String(value)}
            onChange={onChange}
          />
        );
      }
      return (
        <TextInput {...common} value={String(value)} onChange={(e) => onChange(e.currentTarget.value)} />
      );
  }
}
