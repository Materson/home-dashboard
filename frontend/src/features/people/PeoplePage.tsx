/**
 * People — the family members everything else is about. Parents add, edit
 * and archive everyone; a child can edit their own profile when an admin
 * grants "people: edit, self". Each card opens the person's profile.
 */
import { useState } from "react";
import {
  ActionIcon,
  Avatar,
  Badge,
  Button,
  Card,
  Group,
  Popover,
  SimpleGrid,
  Stack,
  Text,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { IconArchive, IconPencil, IconPlus } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { FieldDef, Row } from "@/components/records/fields";
import { RecordFormModal } from "@/components/records/RecordFormModal";
import { usePermissions } from "@/features/auth/usePermissions";
import { ageText } from "@/features/health/ProfileSummary";

import { ageInMonths } from "./age";
import { peopleApi, type Person } from "./api";

export const PERSON_FIELDS: FieldDef[] = [
  { name: "display_name", type: "text", labelKey: "people.f.name", required: true },
  { name: "birth_date", type: "date", labelKey: "people.f.birthDate" },
  { name: "color", type: "color", labelKey: "people.f.color", default: "#4c6ef5" },
];

export function PeoplePage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const canManage = usePermissions().canManage("people");
  const [form, setForm] = useState<Person | null | "new">(null);
  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["people"] });
    qc.invalidateQueries({ queryKey: ["health"] });
  };
  const archive = useMutation({ mutationFn: peopleApi.archive, onSuccess: refresh });

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>{t("people.title")}</Title>
        {canManage && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setForm("new")}>
            {t("people.add")}
          </Button>
        )}
      </Group>

      <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }}>
        {(people.data ?? []).map((p) => (
          <Card key={p.id} withBorder padding="lg">
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              <UnstyledButton component={Link} to={`/people/${p.id}`}>
                <Group wrap="nowrap">
                <Avatar color={p.color} variant="filled" radius="xl" size="lg">
                  {p.display_name.slice(0, 2).toUpperCase()}
                </Avatar>
                <Stack gap={2}>
                  <Text fw={600}>{p.display_name}</Text>
                  <Text size="xs" c="dimmed">
                    {ageText(ageInMonths(p.birth_date), t)}
                  </Text>
                  {p.has_login && (
                    <Badge size="xs" variant="light">
                      {t("people.hasLogin")}
                    </Badge>
                  )}
                </Stack>
                </Group>
              </UnstyledButton>
              <Group gap={4} wrap="nowrap">
                {p.can_edit && (
                  <ActionIcon variant="subtle" aria-label={t("finance.action.edit")} onClick={() => setForm(p)}>
                    <IconPencil size={16} />
                  </ActionIcon>
                )}
                {canManage && (
                  <Popover withArrow>
                    <Popover.Target>
                      <ActionIcon variant="subtle" color="gray" aria-label={t("people.archive")}>
                        <IconArchive size={16} />
                      </ActionIcon>
                    </Popover.Target>
                    <Popover.Dropdown>
                      <Stack gap="xs" maw={240}>
                        <Text size="sm">{t("people.archiveConfirm", { name: p.display_name })}</Text>
                        <Button size="xs" color="red" onClick={() => archive.mutate(p.id)}>
                          {t("people.archive")}
                        </Button>
                      </Stack>
                    </Popover.Dropdown>
                  </Popover>
                )}
              </Group>
            </Group>
          </Card>
        ))}
      </SimpleGrid>

      <RecordFormModal
        fields={PERSON_FIELDS}
        record={form === "new" ? null : (form as Row | null)}
        opened={form !== null}
        onClose={() => setForm(null)}
        onSave={(payload) => peopleApi.save(payload, form && form !== "new" ? form.id : undefined)}
        onSaved={refresh}
        titleKey={{ add: "people.add", edit: "people.edit" }}
      />
    </Stack>
  );
}
