/**
 * A person's profile: their details (editable when allowed) and — with
 * health access — their health at a glance (BMI, trend, treatments, visits).
 */
import { useState } from "react";
import { ActionIcon, Alert, Avatar, Button, Stack, Tooltip } from "@mantine/core";
import { IconArrowLeft, IconHeartbeat, IconPencil } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";

import { Link, useParams } from "react-router-dom";

import type { Row } from "@/components/records/fields";
import { RecordFormModal } from "@/components/records/RecordFormModal";
import { usePermissions } from "@/features/auth/usePermissions";
import { ageText, ProfileSummary } from "@/features/health/ProfileSummary";
import { fmtDate } from "@/lib/format";

import { ageInMonths } from "./age";
import { peopleApi } from "./api";
import { PERSON_FIELDS } from "./PeoplePage";

export function PersonPage() {
  const { t } = useTranslation();
  const { personId = "" } = useParams();
  const qc = useQueryClient();
  const canSeeHealth = usePermissions().canView("health");
  const [editing, setEditing] = useState(false);
  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const person = people.data?.find((p) => p.id === personId);

  if (people.isSuccess && !person) return <Alert color="gray">{t("common.noAccess")}</Alert>;
  if (!person) return null;

  return (
    <Stack gap="lg">
      <PageHeader
        title={person.display_name}
        subtitle={
          person.birth_date
            ? `${fmtDate(person.birth_date)} · ${ageText(ageInMonths(person.birth_date), t)}`
            : t("people.noBirthDate")
        }
        before={
          <Tooltip label={t("people.title")}>
            <ActionIcon component={Link} to="/people" variant="default" size="lg" radius="md" aria-label={t("people.title")}>
              <IconArrowLeft size={18} />
            </ActionIcon>
          </Tooltip>
        }
        icon={
          <Avatar color={person.color} variant="filled" radius="md" size={42}>
            {person.display_name.slice(0, 2).toUpperCase()}
          </Avatar>
        }
        actions={
        <>
          {canSeeHealth && (
            <Button
              variant="light"
              leftSection={<IconHeartbeat size={16} />}
              component={Link}
              to={`/health/${person.id}`}
            >
              {t("people.healthHistory")}
            </Button>
          )}
          {person.can_edit && (
            <Button variant="default" leftSection={<IconPencil size={16} />} onClick={() => setEditing(true)}>
              {t("finance.action.edit")}
            </Button>
          )}
        </>
        }
      />

      {canSeeHealth && <ProfileSummary personId={person.id} />}

      <RecordFormModal
        fields={PERSON_FIELDS}
        record={editing ? (person as unknown as Row) : null}
        opened={editing}
        onClose={() => setEditing(false)}
        onSave={(payload) => peopleApi.save(payload, person.id)}
        onSaved={() => {
          qc.invalidateQueries({ queryKey: ["people"] });
          qc.invalidateQueries({ queryKey: ["health"] });
        }}
        titleKey={{ add: "people.add", edit: "people.edit" }}
      />
    </Stack>
  );
}
