/** Add/edit form for one field-driven record (see `fields.ts`). */
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Modal,
  NumberInput,
  Select,
  Stack,
  TagsInput,
  Textarea,
  TextInput,
} from "@mantine/core";
import { DatePickerInput, DateTimePicker } from "@mantine/dates";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { AmountInput } from "@/components/AmountInput";
import { isoDate, isoDateTime, parseIsoDate } from "@/lib/format";

import {
  applyEdit,
  handTypedOnLoad,
  initialState,
  isValid,
  parseTimes,
  toPayload,
  type Choices,
  type FieldDef,
  type FormState,
  type FormValue,
  type Row,
} from "./fields";

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
}) {
  const { t } = useTranslation();
  const { fields } = props;
  const [state, setState] = useState<FormState>(() => initialState(fields, props.record));
  const [handTyped, setHandTyped] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!props.opened) return;
    const initial = initialState(fields, props.record);
    setState(initial);
    setHandTyped(handTypedOnLoad(fields, initial, !!props.record));
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
    setState(result.state);
  };

  return (
    <Modal
      opened={props.opened}
      onClose={props.onClose}
      title={t(props.record ? props.titleKey.edit : props.titleKey.add)}
    >
      <Stack>
        {fields.map((f) => (
          <Field
            key={f.name}
            def={f}
            value={state[f.name]}
            choices={props.choices?.[f.name]}
            onChange={(v) => set(f.name, v)}
          />
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
  onChange,
}: {
  def: FieldDef;
  value: FormValue;
  choices?: { value: string; label: string }[];
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
    case "datetime":
      return (
        <DateTimePicker
          {...common}
          clearable={!def.required}
          value={value ? new Date(String(value)) : null}
          onChange={(d) => onChange(d ? isoDateTime(d) : "")}
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
    case "times":
      return (
        <TagsInput
          {...common}
          placeholder="08:00"
          splitChars={[",", " "]}
          value={String(value) ? String(value).split(/[,\s]+/).filter(Boolean) : []}
          onChange={(tags) => onChange(tags.join(", "))}
          error={
            String(value).trim() &&
            parseTimes(value).length !== String(value).split(/[,\s]+/).filter(Boolean).length
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
      return (
        <TextInput {...common} value={String(value)} onChange={(e) => onChange(e.currentTarget.value)} />
      );
  }
}
