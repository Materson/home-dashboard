/**
 * An illness / event as the hub: its details plus the visits and treatments
 * that belong to it, plus dated symptoms (to follow how it develops), each
 * addable/editable right here (their forms open on
 * top). Everything added here is an ordinary visit / treatment — it also
 * shows in the Visits and Treatments tabs, and a new medicine name lands in
 * the cabinet.
 */
import { useState } from "react";
import { Badge, Button, Group, Modal, Stack, Text, Title } from "@mantine/core";
import { IconPencil } from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { Row } from "@/components/records/fields";
import { RecordFormModal } from "@/components/records/RecordFormModal";
import { RecordList } from "@/components/records/RecordList";
import { fmtDate, isoDateTime } from "@/lib/format";

import { healthApi, type HealthKind } from "./api";
import { HEALTH_RECORDS } from "./fields";
import { medicationDoseExtra } from "./MedicationDose";
import { HEALTH_INVALIDATE, useHealthForms } from "./useHealthForms";

const LABELS = {
  add: "health.add",
  edit: "health.edit",
  empty: "health.empty",
  deleteConfirm: "health.deleteConfirm",
};

export function EventModal(props: {
  event: Row | null;
  personId: string;
  canEdit: boolean;
  onClose: () => void;
  /** Called with the saved event so the window shows the new details. */
  onUpdated: (event: Row) => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const forms = useHealthForms(props.personId);
  const [editing, setEditing] = useState(false);
  const ev = props.event;

  const section = (kind: HealthKind, titleKey: string) =>
    ev && (
      <Stack gap="xs">
        <Title order={5}>{t(titleKey)}</Title>
        <RecordList
          fields={HEALTH_RECORDS[kind]}
          queryKey={["health", props.personId, kind, { condition: ev.id }]}
          list={() => healthApi.list(kind, { condition_id: ev.id })}
          save={(payload, id) => healthApi.save(kind, payload, id)}
          remove={(id) => healthApi.remove(kind, id)}
          invalidate={HEALTH_INVALIDATE}
          choices={forms.choices}
          suggestions={forms.suggestions}
          fills={forms.fills}
          // A new symptom is "now" unless changed; other kinds ignore observed_at.
          defaults={{
            person_id: String(ev.person_id),
            condition_id: ev.id,
            observed_at: isoDateTime(new Date()),
          }}
          labels={LABELS}
          readOnly={!props.canEdit}
          hiddenColumns={["condition_id"]}
          formExtras={kind === "medications" ? { dosage: medicationDoseExtra(forms.cabinet) } : undefined}
        />
      </Stack>
    );

  return (
    <Modal opened={!!ev} onClose={props.onClose} size="xl" title={ev ? String(ev.title) : ""}>
      {ev && (
        <Stack gap="lg">
          <Group justify="space-between" align="flex-start">
            <Stack gap={4}>
              <Group gap="xs">
                <Badge variant="light">{t(`health.conditionKind.${String(ev.kind)}`)}</Badge>
                <Text size="sm">
                  {fmtDate(String(ev.start_date))} – {ev.end_date ? fmtDate(String(ev.end_date)) : t("health.event.ongoing")}
                </Text>
              </Group>
              {ev.notes ? (
                <Text size="sm" c="dimmed" style={{ whiteSpace: "pre-wrap" }}>
                  {String(ev.notes)}
                </Text>
              ) : null}
            </Stack>
            {props.canEdit && (
              <Button size="xs" variant="light" leftSection={<IconPencil size={14} />} onClick={() => setEditing(true)}>
                {t("finance.action.edit")}
              </Button>
            )}
          </Group>

          {section("symptoms", "health.tab.symptoms")}
          {section("appointments", "health.tab.appointments")}
          {section("medications", "health.tab.treatments")}

          <RecordFormModal
            fields={HEALTH_RECORDS.conditions}
            record={editing ? ev : null}
            opened={editing}
            onClose={() => setEditing(false)}
            onSave={(payload) =>
              healthApi.save("conditions", payload, ev.id).then((saved) => {
                props.onUpdated(saved);
                return saved;
              })
            }
            onSaved={() => {
              for (const key of HEALTH_INVALIDATE) qc.invalidateQueries({ queryKey: key });
            }}
            titleKey={{ add: "health.add", edit: "health.edit" }}
            choices={forms.choices}
            suggestions={forms.suggestions}
          />
        </Stack>
      )}
    </Modal>
  );
}
