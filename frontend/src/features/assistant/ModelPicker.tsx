/**
 * The chat's two model pickers: one answers text, the other messages with
 * photos / PDFs. "Default" follows the AI settings. A private conversation
 * offers local models only; the file picker only models that read files and
 * may get them (Settings → AI → photos and documents).
 */
import { Group, Select } from "@mantine/core";
import { IconMessage, IconPaperclip } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";

import type { ModelChoice, ModelOption, Status } from "./api";

const DEFAULT = "__default";
const STORE = "assistant.models";

/** The models one may pick for text or for files. */
export function modelOptions(status: Status, opts: { files: boolean; isPrivate: boolean }): ModelOption[] {
  return status.models.filter(
    (m) =>
      (!opts.isPrivate || m.location === "local") &&
      (!opts.files ||
        (m.vision && (status.documents === "cloud" || (status.documents === "local" && m.location === "local")))),
  );
}

/** A choice with what can't be picked (any more) back to the default. */
export function validChoice(choice: ModelChoice, status: Status, isPrivate: boolean): ModelChoice {
  const ok = (id: string | null, files: boolean) =>
    id && modelOptions(status, { files, isPrivate }).some((m) => m.id === id) ? id : null;
  return { text_profile_id: ok(choice.text_profile_id, false), file_profile_id: ok(choice.file_profile_id, true) };
}

/** The last picks on this device, for a new conversation. */
export function lastChoice(): ModelChoice {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE) ?? "{}") as Partial<ModelChoice>;
    return { text_profile_id: saved.text_profile_id ?? null, file_profile_id: saved.file_profile_id ?? null };
  } catch {
    return { text_profile_id: null, file_profile_id: null };
  }
}

export function rememberChoice(choice: ModelChoice): void {
  try {
    localStorage.setItem(STORE, JSON.stringify(choice));
  } catch {
    // storage blocked: the defaults next time
  }
}

export function ModelPicker(props: {
  status: Status;
  isPrivate: boolean;
  value: ModelChoice;
  onChange: (v: ModelChoice) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const s = props.status;
  const value = validChoice(props.value, s, props.isPrivate);
  const label = (m: ModelOption) => `${m.name} · ${t(`assistant.location.${m.location}`)}`;
  const textDefault = props.isPrivate ? s.local_profile : s.chat_profile;
  const fileOptions = modelOptions(s, { files: true, isPrivate: props.isPrivate });
  const fileDefault = fileOptions.find((m) => m.id === s.file_profile?.id) ?? null;
  const data = (options: ModelOption[], defaultName: string) => [
    { value: DEFAULT, label: defaultName },
    ...options.map((m) => ({ value: m.id, label: label(m) })),
  ];

  return (
    <Group gap={6} wrap="wrap" style={{ flex: 1, minWidth: 0 }}>
      <Select
        size="xs"
        w={190}
        style={{ flexGrow: 1, maxWidth: 260 }}
        leftSection={<IconMessage size={14} />}
        aria-label={t("assistant.models.text")}
        title={t("assistant.models.text")}
        data={data(
          modelOptions(s, { files: false, isPrivate: props.isPrivate }),
          t("assistant.models.default", { name: textDefault?.name ?? "—" }),
        )}
        value={value.text_profile_id ?? DEFAULT}
        onChange={(v) => v && props.onChange({ ...value, text_profile_id: v === DEFAULT ? null : v })}
        allowDeselect={false}
        disabled={props.disabled}
        comboboxProps={{ withinPortal: true }}
      />
      <Select
        size="xs"
        w={190}
        style={{ flexGrow: 1, maxWidth: 260 }}
        leftSection={<IconPaperclip size={14} />}
        aria-label={t("assistant.models.files")}
        title={t("assistant.models.files")}
        data={data(
          fileOptions,
          fileDefault ? t("assistant.models.default", { name: fileDefault.name }) : t("assistant.models.sameAsText"),
        )}
        value={s.documents === "off" ? null : (value.file_profile_id ?? DEFAULT)}
        onChange={(v) => v && props.onChange({ ...value, file_profile_id: v === DEFAULT ? null : v })}
        allowDeselect={false}
        disabled={props.disabled || s.documents === "off"}
        placeholder={s.documents === "off" ? t("assistant.models.filesOff") : undefined}
        comboboxProps={{ withinPortal: true }}
      />
    </Group>
  );
}
