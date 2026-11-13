/**
 * Access grants of one role or one account (its exceptions): a readable line
 * each ("Finanse — edycja · wszyscy · do 31.12.2026"), and a form to add or
 * change one. A deny takes away its level and every level above it.
 */
import { useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  MultiSelect,
  Popover,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Tooltip,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { peopleApi } from "@/features/people/api";
import { fmtDate, isoDate, parseIsoDate } from "@/lib/format";

import { accessApi, type Grant, type GrantInput, type Level, problemText, type Subjects } from "./api";

type Owner = { user_id: number } | { group_id: number };

export function GrantList(props: { grants: Grant[]; owner: Owner; onChanged: () => void; emptyKey: string }) {
  const { t } = useTranslation();
  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const names = Object.fromEntries((people.data ?? []).map((p) => [p.id, p.display_name]));
  const [editing, setEditing] = useState<Grant | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const remove = useMutation({
    mutationFn: accessApi.deleteGrant,
    onSuccess: props.onChanged,
    onError: (err) => setError(problemText(t, err)),
  });

  return (
    <Stack gap={6}>
      {!props.grants.length && (
        <Text size="sm" c="dimmed">
          {t(props.emptyKey)}
        </Text>
      )}
      {props.grants.map((g) => (
        <Group key={g.id} gap="xs" wrap="nowrap" justify="space-between">
          <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
            <Badge size="sm" variant="light" color={g.effect === "deny" ? "red" : "teal"} style={{ flexShrink: 0 }}>
              {t(`access.effect.${g.effect}`)}
            </Badge>
            <Text size="sm" style={{ minWidth: 0 }}>
              <b>{t(`access.module.${g.module}`)}</b> — {describe(g, t, names)}
            </Text>
          </Group>
          <Group gap={2} wrap="nowrap">
            <Tooltip label={t("finance.action.edit")}>
              <ActionIcon variant="subtle" onClick={() => setEditing(g)} aria-label={t("finance.action.edit")}>
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
                <Stack gap="xs" maw={240}>
                  <Text size="sm">{t("access.deleteConfirm")}</Text>
                  <Button size="xs" color="red" loading={remove.isPending} onClick={() => remove.mutate(g.id)}>
                    {t("finance.action.delete")}
                  </Button>
                </Stack>
              </Popover.Dropdown>
            </Popover>
          </Group>
        </Group>
      ))}
      {error && (
        <Alert color="red" withCloseButton onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      <Group>
        <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEditing("new")}>
          {t("access.add")}
        </Button>
      </Group>
      {editing && (
        <GrantForm
          grant={editing === "new" ? null : editing}
          owner={props.owner}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            props.onChanged();
          }}
        />
      )}
    </Stack>
  );
}

/** "edycja · wybrane: Zosia · dane od 1.01.2024 · do 31.12.2026" */
function describe(g: Grant, t: (k: string, o?: Record<string, unknown>) => string, names: Record<string, string>): string {
  const who =
    g.subjects === "selected"
      ? t("access.whoSelected", { names: g.person_ids.map((id) => names[id] ?? "…").join(", ") })
      : t(`access.subjects.${g.subjects}`);
  return [
    t(`access.level.${g.level}`),
    who,
    g.data_from || g.data_to
      ? t("access.dataWindow", { from: g.data_from ? fmtDate(g.data_from) : "…", to: g.data_to ? fmtDate(g.data_to) : "…" })
      : null,
    g.valid_until ? t("access.until", { date: fmtDate(g.valid_until.slice(0, 10)) }) : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function GrantForm(props: { grant: Grant | null; owner: Owner; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const meta = useQuery({ queryKey: ["access", "meta"], queryFn: accessApi.meta, staleTime: Infinity });
  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const g = props.grant;
  const [module, setModule] = useState<string | null>(g?.module ?? null);
  const [level, setLevel] = useState<Level>(g?.level ?? "view");
  const [effect, setEffect] = useState<"allow" | "deny">(g?.effect ?? "allow");
  const [subjects, setSubjects] = useState<Subjects>(g?.subjects ?? "all");
  const [persons, setPersons] = useState<string[]>(g?.person_ids ?? []);
  const [dataWindow, setDataWindow] = useState<[Date | null, Date | null]>([
    g?.data_from ? parseIsoDate(g.data_from) : null,
    g?.data_to ? parseIsoDate(g.data_to) : null,
  ]);
  const [until, setUntil] = useState<Date | null>(g?.valid_until ? new Date(g.valid_until) : null);
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => {
      const body: GrantInput = {
        user_id: "user_id" in props.owner ? props.owner.user_id : null,
        group_id: "group_id" in props.owner ? props.owner.group_id : null,
        module: module ?? "",
        level,
        effect,
        subjects,
        person_ids: subjects === "selected" ? persons : [],
        data_from: dataWindow[0] ? isoDate(dataWindow[0]) : null,
        data_to: dataWindow[1] ? isoDate(dataWindow[1]) : null,
        // To the end of that day.
        valid_until: until
          ? new Date(until.getFullYear(), until.getMonth(), until.getDate(), 23, 59, 59).toISOString()
          : null,
      };
      return accessApi.saveGrant(body, g?.id);
    },
    onSuccess: props.onSaved,
    onError: (err) => setError(problemText(t, err)),
  });

  return (
    <Modal opened onClose={props.onClose} title={t(g ? "access.editTitle" : "access.addTitle")} size="lg">
      <Stack gap="sm">
        <Select
          label={t("access.f.module")}
          data={(meta.data?.modules ?? []).map((m) => ({ value: m, label: t(`access.module.${m}`) }))}
          value={module}
          onChange={setModule}
          allowDeselect={false}
          required
          searchable
        />
        <Stack gap={4}>
          <Text size="sm" fw={500}>
            {t("access.f.effect")}
          </Text>
          <SegmentedControl
            fullWidth
            value={effect}
            onChange={(v) => setEffect(v as "allow" | "deny")}
            data={[
              { value: "allow", label: t("access.effect.allow") },
              { value: "deny", label: t("access.effect.deny") },
            ]}
          />
        </Stack>
        <Stack gap={4}>
          <Text size="sm" fw={500}>
            {t("access.f.level")}
          </Text>
          <SegmentedControl
            fullWidth
            value={level}
            onChange={(v) => setLevel(v as Level)}
            data={(meta.data?.levels ?? ["view", "edit", "manage"]).map((l) => ({ value: l, label: t(`access.level.${l}`) }))}
          />
          <Text size="xs" c="dimmed">
            {t(effect === "deny" ? "access.denyHint" : `access.levelHint.${level}`)}
          </Text>
        </Stack>
        <Stack gap={4}>
          <Text size="sm" fw={500}>
            {t("access.f.subjects")}
          </Text>
          <SegmentedControl
            fullWidth
            value={subjects}
            onChange={(v) => setSubjects(v as Subjects)}
            data={(["all", "self", "selected"] as const).map((s) => ({ value: s, label: t(`access.subjects.${s}`) }))}
          />
          <Text size="xs" c="dimmed">
            {t(`access.subjectsHint.${subjects}`)}
          </Text>
        </Stack>
        {subjects === "selected" && (
          <MultiSelect
            label={t("access.f.persons")}
            data={(people.data ?? []).map((p) => ({ value: p.id, label: p.display_name }))}
            value={persons}
            onChange={setPersons}
            required
          />
        )}
        <DatePickerInput
          type="range"
          allowSingleDateInRange
          clearable
          label={t("access.f.dataWindow")}
          description={t("access.f.dataWindowHint")}
          valueFormat="DD.MM.YYYY"
          value={dataWindow}
          onChange={setDataWindow}
        />
        <DatePickerInput
          clearable
          label={t("access.f.validUntil")}
          description={t("access.f.validUntilHint")}
          valueFormat="DD.MM.YYYY"
          value={until}
          onChange={setUntil}
          minDate={new Date()}
        />
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={props.onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            loading={save.isPending}
            disabled={!module || (subjects === "selected" && !persons.length)}
            onClick={() => {
              setError(null);
              save.mutate();
            }}
          >
            {t("finance.action.save")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
