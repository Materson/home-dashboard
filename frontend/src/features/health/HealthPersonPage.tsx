/**
 * One person's health: profile (BMI, trend, current treatments, upcoming
 * visits), today's doses, and their history in tabs. New entries default to
 * this person (the form's "Person" field can change it). Clicking an
 * illness/event opens it as a hub for its symptoms, visits and treatments;
 * the Symptoms tab follows all of them over time.
 */
import { useState } from "react";
import {
  ActionIcon,
  Anchor,
  Badge,
  Group,
  Paper,
  Stack,
  Tabs,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconArrowLeft, IconPaperclip } from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import type { Row } from "@/components/records/fields";
import { RecordList } from "@/components/records/RecordList";
import { usePermissions } from "@/features/auth/usePermissions";
import { isoDateTime } from "@/lib/format";

import { healthApi, type HealthKind } from "./api";
import { DosesCard } from "./DosesCard";
import { medicationDoseExtra } from "./MedicationDose";
import { EventModal } from "./EventModal";
import { HEALTH_RECORDS, HEALTH_TABS } from "./fields";
import { ProfileSummary } from "./ProfileSummary";
import { ResultFiles } from "./ResultFiles";
import { HEALTH_INVALIDATE, useHealthForms } from "./useHealthForms";

const LABELS = {
  add: "health.add",
  edit: "health.edit",
  empty: "health.empty",
  deleteConfirm: "health.deleteConfirm",
};

export function HealthPersonPage() {
  const { t } = useTranslation();
  const { personId = "" } = useParams();
  const qc = useQueryClient();
  const canEdit = usePermissions().canEdit("health");
  const forms = useHealthForms(personId);
  const [event, setEvent] = useState<Row | null>(null);
  const [filesFor, setFilesFor] = useState<{ id: string; title: string } | null>(null);
  const name = forms.people.find((p) => p.id === personId)?.display_name ?? "";

  const list = (kind: HealthKind) => (
    <RecordList
      fields={HEALTH_RECORDS[kind]}
      queryKey={["health", personId, kind]}
      list={() => healthApi.list(kind, { person_id: personId })}
      save={(payload, id) => healthApi.save(kind, payload, id)}
      remove={(id) => healthApi.remove(kind, id)}
      invalidate={HEALTH_INVALIDATE}
      choices={forms.choices}
      suggestions={forms.suggestions}
      fills={forms.fills}
      defaults={{ person_id: personId, observed_at: isoDateTime(new Date()) }}
      formExtras={kind === "medications" ? { dosage: medicationDoseExtra(forms.cabinet) } : undefined}
      labels={LABELS}
      readOnly={!canEdit}
      onRowClick={kind === "conditions" ? setEvent : undefined}
      extraColumns={
        kind === "results"
          ? [
              {
                headerKey: "health.files.title",
                render: (r) =>
                  Number(r.attachments) > 0 ? <Badge variant="light">{String(r.attachments)}</Badge> : "—",
              },
            ]
          : undefined
      }
      rowActions={
        kind === "results"
          ? (r) => (
              <Tooltip label={t("health.files.title")}>
                <ActionIcon variant="subtle" onClick={() => setFilesFor({ id: r.id, title: String(r.title) })}>
                  <IconPaperclip size={16} />
                </ActionIcon>
              </Tooltip>
            )
          : undefined
      }
    />
  );

  return (
    <Stack gap="lg">
      <Group>
        <Anchor component={Link} to="/health" c="dimmed">
          <Group gap={4}>
            <IconArrowLeft size={16} />
            {t("health.choose.back")}
          </Group>
        </Anchor>
        <Title order={2}>{name}</Title>
      </Group>

      <ProfileSummary personId={personId} />
      <DosesCard personId={personId} />

      <Paper withBorder p="md">
        <Tabs defaultValue="conditions" keepMounted={false}>
          <Tabs.List>
            {HEALTH_TABS.map((tab) => (
              <Tabs.Tab key={tab.kind} value={tab.kind}>
                {t(tab.labelKey)}
              </Tabs.Tab>
            ))}
          </Tabs.List>
          {HEALTH_TABS.map((tab) => (
            <Tabs.Panel key={tab.kind} value={tab.kind} pt="md">
              {tab.kind === "conditions" && (
                <Text size="xs" c="dimmed">
                  {t("health.event.clickHint")}
                </Text>
              )}
              {list(tab.kind)}
            </Tabs.Panel>
          ))}
        </Tabs>
      </Paper>

      <EventModal
        event={event}
        personId={personId}
        canEdit={canEdit}
        onClose={() => setEvent(null)}
        onUpdated={setEvent}
      />
      <ResultFiles
        resultId={filesFor?.id ?? null}
        title={filesFor?.title ?? ""}
        canEdit={canEdit}
        onClose={() => setFilesFor(null)}
        onChanged={() => qc.invalidateQueries({ queryKey: ["health", personId, "results"] })}
      />
    </Stack>
  );
}
