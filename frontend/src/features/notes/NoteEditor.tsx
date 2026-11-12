/**
 * Add / edit a note: text, checklist, reminder (date + 24h time, repeat,
 * also remind others), sharing (owner only: nobody / view / edit per family
 * member) and files. Shared view-only notes open read-only.
 */
import { useEffect, useState } from "react";
import {
  ActionIcon,
  Alert,
  Button,
  Checkbox,
  Divider,
  Group,
  Modal,
  MultiSelect,
  Popover,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { IconArchive, IconArchiveOff, IconPin, IconPinFilled, IconPlus, IconTrash, IconX } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Attachments } from "@/components/Attachments";
import { TimeField } from "@/components/TimeField";
import { normalizeTime } from "@/components/records/fields";
import { isoDate, parseIsoDate } from "@/lib/format";

import { type ChecklistItem, type Note, notesApi, type Repeat } from "./api";

type Access = "none" | "view" | "edit";

/** What a new note starts with (e.g. from the quick-add bar). */
export type NoteDraft = { title?: string; remind_at?: string | null; repeat?: Repeat };

const pad = (n: number) => String(n).padStart(2, "0");
const timeOf = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

export function NoteEditor(props: {
  /** An existing note, a draft for a new one, or null (closed). */
  note: Note | null;
  draft: NoteDraft | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const opened = props.note !== null || props.draft !== null;
  return (
    <Modal opened={opened} onClose={props.onClose} size="lg" withCloseButton={false} padding="lg">
      {opened && (
        <Editor
          key={props.note?.id ?? "new"}
          note={props.note}
          draft={props.draft ?? {}}
          onClose={props.onClose}
          onChanged={props.onChanged}
        />
      )}
    </Modal>
  );
}

function Editor({
  note,
  draft,
  onClose,
  onChanged,
}: {
  note: Note | null;
  draft: NoteDraft;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const isNew = note === null;
  const readOnly = !isNew && !note.can_edit;
  const isOwner = isNew || note.is_owner;
  const start = note?.remind_at ?? draft.remind_at ?? null;
  const startDate = start ? new Date(start) : null;

  const [title, setTitle] = useState(note?.title ?? draft.title ?? "");
  const [body, setBody] = useState(note?.body ?? "");
  const [items, setItems] = useState<ChecklistItem[]>(note?.checklist ?? []);
  const [pinned, setPinned] = useState(note?.pinned ?? false);
  const [day, setDay] = useState<string | null>(startDate ? isoDate(startDate) : null);
  const [time, setTime] = useState(startDate ? timeOf(startDate) : "");
  const [repeat, setRepeat] = useState<Repeat>(note?.repeat ?? draft.repeat ?? "");
  const [others, setOthers] = useState<string[]>((note?.remind_others ?? []).map(String));
  const [access, setAccess] = useState<Record<number, Access>>(() =>
    Object.fromEntries((note?.shares ?? []).map((s) => [s.user_id, s.can_edit ? "edit" : "view"])),
  );

  const people = useQuery({ queryKey: ["notes", "people"], queryFn: notesApi.people });
  // An existing note's pin is saved at once; a new note's goes with "Zapisz".
  const pin = useMutation({
    mutationFn: (value: boolean) => notesApi.pin(note!.id, value),
    onSuccess: (saved) => {
      setPinned(saved.pinned);
      onChanged();
    },
  });
  // Reminding someone shares the note with them (view at least).
  useEffect(() => {
    setAccess((a) => {
      const next = { ...a };
      for (const id of others) if (!next[Number(id)] || next[Number(id)] === "none") next[Number(id)] = "view";
      return next;
    });
  }, [others]);

  const badTime = time.trim() !== "" && normalizeTime(time) === null;
  const empty = !title.trim() && !body.trim() && !items.some((i) => i.text.trim());
  const remindAt = day ? `${day}T${normalizeTime(time) ?? "09:00"}` : null;

  const save = useMutation({
    mutationFn: async () => {
      const saved = await notesApi.save(
        {
          title,
          body,
          checklist: items,
          pinned,
          remind_at: remindAt,
          repeat: remindAt ? repeat : "",
          remind_others: remindAt ? others.map(Number) : [],
        },
        note?.id,
      );
      if (isOwner) {
        const shares = Object.entries(access)
          .filter(([, a]) => a !== "none")
          .map(([id, a]) => ({ user_id: Number(id), can_edit: a === "edit" }));
        const before = JSON.stringify(
          (note?.shares ?? []).map((s) => ({ user_id: s.user_id, can_edit: s.can_edit })).sort((a, b) => a.user_id - b.user_id),
        );
        if (JSON.stringify([...shares].sort((a, b) => a.user_id - b.user_id)) !== before) {
          await notesApi.setShares(saved.id, shares);
        }
      }
      return saved;
    },
    onSuccess: () => {
      onChanged();
      onClose();
    },
  });
  const archive = useMutation({
    mutationFn: () => notesApi.archive(note!.id, !note!.archived),
    onSuccess: () => {
      onChanged();
      onClose();
    },
  });
  const remove = useMutation({
    mutationFn: () => notesApi.remove(note!.id),
    onSuccess: () => {
      onChanged();
      onClose();
    },
  });

  const setItem = (i: number, patch: Partial<ChecklistItem>) =>
    setItems((list) => list.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  const addItem = () => setItems((list) => [...list, { text: "", done: false }]);

  const peopleOptions = (people.data ?? []).map((p) => ({ value: String(p.user_id), label: p.name }));

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <TextInput
          variant="unstyled"
          size="lg"
          fw={600}
          style={{ flex: 1 }}
          placeholder={t("notes.f.title")}
          value={title}
          readOnly={readOnly}
          onChange={(e) => setTitle(e.currentTarget.value)}
          data-autofocus
        />
        <Group gap={4} wrap="nowrap">
          {!readOnly && (
            <Tooltip label={t(pinned ? "notes.unpin" : "notes.pin")}>
              <ActionIcon
                variant="subtle"
                loading={pin.isPending}
                onClick={() => (isNew ? setPinned((p) => !p) : pin.mutate(!pinned))}
              >
                {pinned ? <IconPinFilled size={18} /> : <IconPin size={18} />}
              </ActionIcon>
            </Tooltip>
          )}
          <ActionIcon variant="subtle" color="gray" onClick={onClose} aria-label={t("common.close")}>
            <IconX size={18} />
          </ActionIcon>
        </Group>
      </Group>
      {!isNew && !note.is_owner && (
        <Text size="xs" c="dimmed">
          {t(note.can_edit ? "notes.sharedEdit" : "notes.sharedView", { name: note.owner_name })}
        </Text>
      )}

      <Textarea
        autosize
        minRows={3}
        placeholder={t("notes.f.body")}
        value={body}
        readOnly={readOnly}
        onChange={(e) => setBody(e.currentTarget.value)}
      />

      {/* Checklist */}
      <Stack gap={4}>
        {items.map((it, i) => (
          <Group key={i} gap="xs" wrap="nowrap">
            <Checkbox checked={it.done} disabled={readOnly} onChange={(e) => setItem(i, { done: e.currentTarget.checked })} />
            <TextInput
              variant="unstyled"
              style={{ flex: 1 }}
              value={it.text}
              readOnly={readOnly}
              td={it.done ? "line-through" : undefined}
              placeholder={t("notes.itemPlaceholder")}
              onChange={(e) => setItem(i, { text: e.currentTarget.value })}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addItem();
                }
              }}
              autoFocus={i === items.length - 1 && !it.text}
            />
            {!readOnly && (
              <ActionIcon variant="subtle" color="gray" onClick={() => setItems((l) => l.filter((_, j) => j !== i))}>
                <IconX size={14} />
              </ActionIcon>
            )}
          </Group>
        ))}
        {!readOnly && (
          <Button size="xs" variant="subtle" leftSection={<IconPlus size={14} />} onClick={addItem} style={{ alignSelf: "flex-start" }}>
            {t("notes.addItem")}
          </Button>
        )}
      </Stack>

      <Divider label={t("notes.reminder")} labelPosition="left" />
      <Group grow align="flex-start">
        <DatePickerInput
          label={t("notes.f.day")}
          clearable
          disabled={readOnly}
          value={day ? parseIsoDate(day) : null}
          onChange={(d) => setDay(d ? isoDate(d) : null)}
        />
        <TimeField label={t("notes.f.time")} value={time} onChange={setTime} />
        <Select
          label={t("notes.f.repeat")}
          disabled={readOnly || !day}
          allowDeselect={false}
          value={repeat}
          onChange={(v) => setRepeat((v ?? "") as Repeat)}
          data={(["", "daily", "weekly", "monthly"] as Repeat[]).map((r) => ({
            value: r,
            label: t(`notes.repeat.${r || "none"}`),
          }))}
        />
      </Group>
      {day && !time && (
        <Text size="xs" c="dimmed">
          {t("notes.defaultTime")}
        </Text>
      )}
      {day && peopleOptions.length > 0 && (
        <MultiSelect
          label={t("notes.f.remindOthers")}
          disabled={readOnly}
          data={peopleOptions}
          value={others}
          onChange={setOthers}
          clearable
        />
      )}

      {isOwner && peopleOptions.length > 0 && (
        <>
          <Divider label={t("notes.sharing")} labelPosition="left" />
          <Stack gap={6}>
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
        </>
      )}

      <Divider label={t("notes.files")} labelPosition="left" />
      {isNew ? (
        <Text size="xs" c="dimmed">
          {t("notes.filesAfterSave")}
        </Text>
      ) : (
        <Attachments subjectType="notes.note" subjectId={note.id} canEdit={note.can_edit} onChanged={onChanged} />
      )}

      {save.isError && <Alert color="red">{t("common.saveFailed")}</Alert>}
      <Group justify="space-between">
        <Group gap="xs">
          {!isNew && note.is_owner && (
            <>
              <Button
                variant="subtle"
                color="gray"
                leftSection={note.archived ? <IconArchiveOff size={16} /> : <IconArchive size={16} />}
                onClick={() => archive.mutate()}
                loading={archive.isPending}
              >
                {t(note.archived ? "notes.unarchive" : "notes.archive")}
              </Button>
              <Popover withArrow>
                <Popover.Target>
                  <Button variant="subtle" color="red" leftSection={<IconTrash size={16} />}>
                    {t("finance.action.delete")}
                  </Button>
                </Popover.Target>
                <Popover.Dropdown>
                  <Stack gap="xs" maw={240}>
                    <Title order={6}>{t("notes.deleteConfirm")}</Title>
                    <Button size="xs" color="red" onClick={() => remove.mutate()} loading={remove.isPending}>
                      {t("finance.action.delete")}
                    </Button>
                  </Stack>
                </Popover.Dropdown>
              </Popover>
            </>
          )}
        </Group>
        {!readOnly && (
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={empty || badTime}>
            {t("finance.action.save")}
          </Button>
        )}
      </Group>
    </Stack>
  );
}
