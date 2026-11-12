/**
 * Notatki — quick add on top ("jutro 18:00 kupić mleko": the time becomes a
 * reminder, shown before saving), then your notes and the ones shared with
 * you as cards. Pinned first. On a card: tick the checklist, pin, archive.
 * "Zaznacz" selects several of your own notes to archive / restore / delete
 * at once. "/notes?open=<id>" (from a notification) opens that note.
 */
import { useEffect, useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Checkbox,
  Group,
  Paper,
  Popover,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import {
  IconAlarm,
  IconArchive,
  IconArchiveOff,
  IconArrowsMaximize,
  IconChecks,
  IconPaperclip,
  IconPin,
  IconPinFilled,
  IconRepeat,
  IconSearch,
  IconSend,
  IconTrash,
  IconUsers,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { usePermissions } from "@/features/auth/usePermissions";
import { fmtDateTime } from "@/lib/format";

import { type BulkAction, type Note, NOTES_KEY, notesApi, type Scope } from "./api";
import { type NoteDraft, NoteEditor } from "./NoteEditor";

const CARD_ITEMS = 6;

export function NotesPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const canEdit = usePermissions().canEdit("notes");
  const [params, setParams] = useSearchParams();
  const [scope, setScope] = useState<Scope>("all");
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search, 250);
  const [archived, setArchived] = useState(false);
  const [editing, setEditing] = useState<Note | null>(null);
  const [draft, setDraft] = useState<NoteDraft | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const notes = useQuery({
    queryKey: [...NOTES_KEY, scope, q, archived],
    queryFn: () => notesApi.list(scope, q, archived),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: NOTES_KEY });

  const stopSelecting = () => {
    setSelecting(false);
    setSelected(new Set());
  };
  // A different list → a fresh selection.
  useEffect(() => setSelected(new Set()), [scope, q, archived]);

  const bulk = useMutation({
    mutationFn: (action: BulkAction) => notesApi.bulk([...selected], action),
    onSuccess: () => {
      stopSelecting();
      refresh();
    },
  });

  // Opened from a notification: /notes?open=<id>
  const openId = params.get("open");
  useEffect(() => {
    if (!openId) return;
    notesApi
      .get(openId)
      .then(setEditing)
      .catch(() => undefined)
      .finally(() => setParams({}, { replace: true }));
  }, [openId, setParams]);

  const own = (notes.data ?? []).filter((n) => n.is_owner);
  const toggleSelected = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <Stack gap="lg">
      <Title order={2}>{t("notes.title")}</Title>
      {canEdit && <QuickAdd onAdded={refresh} onMore={(d) => setDraft(d)} />}

      <Group justify="space-between">
        <Group>
          <SegmentedControl
            value={scope}
            onChange={(v) => setScope(v as Scope)}
            data={[
              { value: "all", label: t("notes.scope.all") },
              { value: "mine", label: t("notes.scope.mine") },
              { value: "shared", label: t("notes.scope.shared") },
            ]}
          />
          <TextInput
            leftSection={<IconSearch size={16} />}
            placeholder={t("notes.search")}
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
            w={240}
          />
          <Switch label={t("notes.showArchived")} checked={archived} onChange={(e) => setArchived(e.currentTarget.checked)} />
        </Group>
        {canEdit && own.length > 0 && !selecting && (
          <Button variant="subtle" leftSection={<IconChecks size={16} />} onClick={() => setSelecting(true)}>
            {t("notes.select")}
          </Button>
        )}
      </Group>

      {selecting && (
        <Paper withBorder p="sm" pos="sticky" top={70} style={{ zIndex: 5 }}>
          <Group justify="space-between">
            <Group gap="xs">
              <Text size="sm" fw={600}>
                {t("notes.selectedCount", { count: selected.size })}
              </Text>
              <Button
                size="xs"
                variant="subtle"
                onClick={() =>
                  setSelected(selected.size === own.length ? new Set() : new Set(own.map((n) => n.id)))
                }
              >
                {t(selected.size === own.length ? "notes.selectNone" : "notes.selectAll")}
              </Button>
            </Group>
            <Group gap="xs">
              <Button
                size="xs"
                variant="light"
                disabled={!selected.size}
                loading={bulk.isPending && bulk.variables !== "delete"}
                leftSection={archived ? <IconArchiveOff size={14} /> : <IconArchive size={14} />}
                onClick={() => bulk.mutate(archived ? "unarchive" : "archive")}
              >
                {t(archived ? "notes.unarchive" : "notes.archive")}
              </Button>
              <Popover withArrow>
                <Popover.Target>
                  <Button size="xs" variant="light" color="red" disabled={!selected.size} leftSection={<IconTrash size={14} />}>
                    {t("finance.action.delete")}
                  </Button>
                </Popover.Target>
                <Popover.Dropdown>
                  <Stack gap="xs" maw={240}>
                    <Text size="sm">{t("notes.bulkDeleteConfirm", { count: selected.size })}</Text>
                    <Button
                      size="xs"
                      color="red"
                      loading={bulk.isPending && bulk.variables === "delete"}
                      onClick={() => bulk.mutate("delete")}
                    >
                      {t("finance.action.delete")}
                    </Button>
                  </Stack>
                </Popover.Dropdown>
              </Popover>
              <Button size="xs" variant="subtle" color="gray" onClick={stopSelecting}>
                {t("notes.cancel")}
              </Button>
            </Group>
          </Group>
          {own.length < (notes.data?.length ?? 0) && (
            <Text size="xs" c="dimmed" mt={4}>
              {t("notes.onlyOwnSelectable")}
            </Text>
          )}
        </Paper>
      )}

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {(notes.data ?? []).map((n) => (
          <NoteCard
            key={n.id}
            note={n}
            selecting={selecting}
            selected={selected.has(n.id)}
            onSelect={() => toggleSelected(n.id)}
            onOpen={() => setEditing(n)}
            onChanged={refresh}
          />
        ))}
      </SimpleGrid>
      {notes.isSuccess && !notes.data.length && (
        <Text c="dimmed" ta="center" py="xl">
          {search ? t("notes.noMatches") : archived ? t("notes.noArchived") : t("notes.empty")}
        </Text>
      )}

      <NoteEditor
        note={editing}
        draft={draft}
        onClose={() => {
          setEditing(null);
          setDraft(null);
        }}
        onChanged={refresh}
      />
    </Stack>
  );
}

function QuickAdd({ onAdded, onMore }: { onAdded: () => void; onMore: (d: NoteDraft) => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [debounced] = useDebouncedValue(text.trim(), 300);
  const preview = useQuery({
    queryKey: ["notes", "parse", debounced],
    queryFn: () => notesApi.parse(debounced),
    enabled: debounced.length >= 3,
    staleTime: 60_000,
  });
  const add = useMutation({
    mutationFn: () => notesApi.quick(text),
    onSuccess: () => {
      setText("");
      onAdded();
    },
  });
  const p = debounced === text.trim() ? preview.data : undefined;

  return (
    <Paper withBorder p="sm">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) add.mutate();
        }}
      >
        <Group wrap="nowrap" gap="xs">
          <TextInput
            style={{ flex: 1 }}
            placeholder={t("notes.quickPlaceholder")}
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
          />
          <Tooltip label={t("notes.more")}>
            <ActionIcon
              variant="light"
              size="lg"
              onClick={() => {
                onMore({ title: p?.title ?? text, remind_at: p?.remind_at ?? null, repeat: p?.repeat ?? "" });
                setText("");
              }}
            >
              <IconArrowsMaximize size={18} />
            </ActionIcon>
          </Tooltip>
          <ActionIcon type="submit" size="lg" disabled={!text.trim()} loading={add.isPending} aria-label={t("notes.add")}>
            <IconSend size={18} />
          </ActionIcon>
        </Group>
      </form>
      {text.trim().length >= 3 && p?.remind_at && (
        <Group gap="xs" mt={6}>
          <Badge leftSection={<IconAlarm size={12} />} variant="light">
            {fmtDateTime(p.remind_at)}
          </Badge>
          {p.repeat && (
            <Badge leftSection={<IconRepeat size={12} />} variant="light" color="grape">
              {t(`notes.repeat.${p.repeat}`)}
            </Badge>
          )}
          <Text size="sm" c="dimmed">
            {p.title}
          </Text>
        </Group>
      )}
    </Paper>
  );
}

function NoteCard(props: {
  note: Note;
  selecting: boolean;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const { note, selecting } = props;
  const toggle = useMutation({
    mutationFn: (v: { index: number; done: boolean }) => notesApi.toggle(note.id, v.index, v.done),
    onSuccess: props.onChanged,
  });
  const pin = useMutation({ mutationFn: () => notesApi.pin(note.id, !note.pinned), onSuccess: props.onChanged });
  const archive = useMutation({
    mutationFn: () => notesApi.archive(note.id, !note.archived),
    onSuccess: props.onChanged,
  });
  const overdue = note.remind_at && !note.repeat && new Date(note.remind_at) < new Date();
  const shown = note.checklist.slice(0, CARD_ITEMS);
  const selectable = selecting && note.is_owner;

  return (
    <Paper
      withBorder
      p="md"
      onClick={selecting ? (selectable ? props.onSelect : undefined) : props.onOpen}
      style={{
        cursor: selecting && !selectable ? "default" : "pointer",
        outline: props.selected ? "2px solid var(--mantine-primary-color-filled)" : undefined,
      }}
      opacity={(selecting && !selectable) || note.archived ? 0.6 : 1}
    >
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Group gap="xs" wrap="nowrap" align="flex-start">
            {selectable && (
              <Checkbox checked={props.selected} onChange={props.onSelect} onClick={(e) => e.stopPropagation()} aria-label={t("notes.select")} />
            )}
            <Text fw={600} lineClamp={2}>
              {note.title || note.body.split("\n")[0] || t("notes.untitled")}
            </Text>
          </Group>
          <Group gap={2} wrap="nowrap" onClick={(e) => e.stopPropagation()}>
            {(note.shares.length > 0 || !note.is_owner) && (
              <Tooltip label={note.is_owner ? note.shares.map((s) => s.name).join(", ") : t("notes.from", { name: note.owner_name })}>
                <IconUsers size={16} style={{ margin: "0 4px" }} />
              </Tooltip>
            )}
            {!selecting && note.can_edit ? (
              <Tooltip label={t(note.pinned ? "notes.unpin" : "notes.pin")}>
                <ActionIcon variant="subtle" color={note.pinned ? undefined : "gray"} size="sm" loading={pin.isPending} onClick={() => pin.mutate()}>
                  {note.pinned ? <IconPinFilled size={16} /> : <IconPin size={16} />}
                </ActionIcon>
              </Tooltip>
            ) : (
              note.pinned && <IconPinFilled size={16} style={{ margin: "0 4px" }} />
            )}
            {!selecting && note.is_owner && (
              <Tooltip label={t(note.archived ? "notes.unarchive" : "notes.archive")}>
                <ActionIcon variant="subtle" color="gray" size="sm" loading={archive.isPending} onClick={() => archive.mutate()}>
                  {note.archived ? <IconArchiveOff size={16} /> : <IconArchive size={16} />}
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
        </Group>
        {note.body && note.title && (
          <Text size="sm" lineClamp={6} style={{ whiteSpace: "pre-wrap" }}>
            {note.body}
          </Text>
        )}
        {shown.length > 0 && (
          <Stack gap={2} onClick={(e) => !selecting && e.stopPropagation()}>
            {shown.map((it, i) => (
              <Checkbox
                key={i}
                size="xs"
                checked={it.done}
                disabled={!note.can_edit || selecting}
                label={
                  <Text size="sm" td={it.done ? "line-through" : undefined} c={it.done ? "dimmed" : undefined}>
                    {it.text}
                  </Text>
                }
                onChange={(e) => toggle.mutate({ index: i, done: e.currentTarget.checked })}
              />
            ))}
            {note.checklist.length > CARD_ITEMS && (
              <Button size="compact-xs" variant="subtle" onClick={props.onOpen} style={{ alignSelf: "flex-start" }}>
                {t("notes.moreItems", { count: note.checklist.length - CARD_ITEMS })}
              </Button>
            )}
          </Stack>
        )}
        {(note.remind_at || note.attachments > 0) && (
          <Group gap={6}>
            {note.remind_at && (
              <Badge
                size="sm"
                variant="light"
                color={overdue ? "gray" : "blue"}
                leftSection={note.repeat ? <IconRepeat size={11} /> : <IconAlarm size={11} />}
              >
                {fmtDateTime(note.remind_at)}
              </Badge>
            )}
            {note.attachments > 0 && (
              <Badge size="sm" variant="light" color="gray" leftSection={<IconPaperclip size={11} />}>
                {note.attachments}
              </Badge>
            )}
          </Group>
        )}
      </Stack>
    </Paper>
  );
}
