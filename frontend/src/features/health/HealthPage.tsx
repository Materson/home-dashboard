/**
 * Health — pick a person, see today's medicine doses, and manage their
 * history in tabs: illnesses, medicines (with dose reminders), doctor
 * visits, test results (with files) and medicine purchases.
 *
 * The person list comes from the health scope, so a child only sees
 * themself. Without health:edit the tabs are read-only (doses can still be
 * confirmed).
 */
import { useEffect, useMemo, useState } from "react";
import { ActionIcon, Alert, Badge, Group, Paper, SegmentedControl, Stack, Tabs, Title, Tooltip } from "@mantine/core";
import { IconPaperclip } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { Choices } from "@/components/records/fields";
import { RecordList } from "@/components/records/RecordList";
import { usePermissions } from "@/features/auth/usePermissions";

import { healthApi, type HealthKind } from "./api";
import { DosesCard } from "./DosesCard";
import { HEALTH_RECORDS, HEALTH_TABS } from "./fields";
import { ResultFiles } from "./ResultFiles";

const LABELS = {
  add: "health.add",
  edit: "health.edit",
  empty: "health.empty",
  deleteConfirm: "health.deleteConfirm",
};

export function HealthPage() {
  const { t } = useTranslation();
  const perms = usePermissions();
  const canEdit = perms.canEdit("health");
  const people = useQuery({ queryKey: ["health", "people"], queryFn: () => healthApi.people() });
  const [personId, setPersonId] = useState<string | null>(null);

  useEffect(() => {
    if (!personId && people.data?.length) setPersonId(people.data[0].id);
  }, [people.data, personId]);

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>{t("nav.health")}</Title>
        {!!people.data && people.data.length > 1 && (
          <SegmentedControl
            data={people.data.map((p) => ({ value: p.id, label: p.display_name }))}
            value={personId ?? undefined}
            onChange={setPersonId}
          />
        )}
      </Group>

      {people.isSuccess && !people.data.length && <Alert color="gray">{t("health.noPeople")}</Alert>}

      {personId && (
        <>
          <DosesCard personId={personId} />
          <PersonRecords personId={personId} canEdit={canEdit} />
        </>
      )}
    </Stack>
  );
}

function PersonRecords({ personId, canEdit }: { personId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [filesFor, setFilesFor] = useState<{ id: string; title: string } | null>(null);

  // Options for the "for illness" / "medicine" pickers come from this person's records.
  const conditions = useQuery({
    queryKey: ["health", personId, "conditions"],
    queryFn: () => healthApi.list("conditions", personId),
  });
  const medications = useQuery({
    queryKey: ["health", personId, "medications"],
    queryFn: () => healthApi.list("medications", personId),
  });
  const choices: Choices = useMemo(
    () => ({
      condition_id: (conditions.data ?? []).map((c) => ({ value: c.id, label: String(c.title) })),
      medication_id: (medications.data ?? []).map((m) => ({ value: m.id, label: String(m.name) })),
    }),
    [conditions.data, medications.data],
  );

  const list = (kind: HealthKind) => (
    <RecordList
      fields={HEALTH_RECORDS[kind]}
      queryKey={["health", personId, kind]}
      list={() => healthApi.list(kind, personId)}
      save={(payload, id) => healthApi.save(kind, { ...payload, person_id: personId }, id)}
      remove={(id) => healthApi.remove(kind, id)}
      // Medicines change the dose plan; costs land in Finance.
      invalidate={[["health", "doses", personId], ["finance"]]}
      choices={choices}
      labels={LABELS}
      readOnly={!canEdit}
      extraColumns={
        kind === "results"
          ? [
              {
                headerKey: "health.files.title",
                render: (r) =>
                  Number(r.attachments) > 0 ? (
                    <Badge variant="light">{String(r.attachments)}</Badge>
                  ) : (
                    "—"
                  ),
              },
            ]
          : undefined
      }
      rowActions={
        kind === "results"
          ? (r) => (
              <Tooltip label={t("health.files.title")}>
                <ActionIcon
                  variant="subtle"
                  onClick={() => setFilesFor({ id: r.id, title: String(r.title) })}
                >
                  <IconPaperclip size={16} />
                </ActionIcon>
              </Tooltip>
            )
          : undefined
      }
    />
  );

  return (
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
            {list(tab.kind)}
          </Tabs.Panel>
        ))}
      </Tabs>

      <ResultFiles
        resultId={filesFor?.id ?? null}
        title={filesFor?.title ?? ""}
        canEdit={canEdit}
        onClose={() => setFilesFor(null)}
        onChanged={() => qc.invalidateQueries({ queryKey: ["health", personId, "results"] })}
      />
    </Paper>
  );
}
