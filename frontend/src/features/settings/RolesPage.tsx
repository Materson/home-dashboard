/**
 * Settings → Roles and access (admins): what each role may see and do. An
 * account gets every grant of its roles, plus its own exceptions (Accounts);
 * a deny wins. Admin / Parent / Child are built in: their grants can change,
 * their names can't (the start-up seed finds them by name).
 */
import { useState } from "react";
import { ActionIcon, Alert, Badge, Button, Group, Modal, Paper, Popover, Stack, Text, TextInput, Title, Tooltip } from "@mantine/core";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/PageHeader";

import { accessApi, problemText, type Role } from "./api";
import { GrantList } from "./GrantList";
import { roleLabel, SettingsNav } from "./parts";

export function RolesPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const roles = useQuery({ queryKey: ["access", "roles"], queryFn: accessApi.roles });
  const [naming, setNaming] = useState<Role | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["access"] });
  const remove = useMutation({
    mutationFn: accessApi.deleteRole,
    onSuccess: () => {
      refresh();
      void qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err) => setError(problemText(t, err)),
  });

  return (
    <Stack gap="lg">
      <PageHeader
        title={t("settings.section.roles")}
        subtitle={t("roles.subtitle")}
        actions={
          <>
            <SettingsNav />
            <Button leftSection={<IconPlus size={16} />} onClick={() => setNaming("new")}>
              {t("roles.add")}
            </Button>
          </>
        }
      />
      <Text size="sm" c="dimmed" maw={760}>
        {t("roles.howItWorks")}
      </Text>
      {error && (
        <Alert color="red" withCloseButton onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {(roles.data ?? []).map((r) => (
        <Paper key={r.id} withBorder p="md">
          <Group justify="space-between" mb="sm" wrap="nowrap" align="flex-start">
            <Group gap="xs">
              <Title order={5}>{roleLabel(r.name, t)}</Title>
              {r.builtin && (
                <Badge size="xs" variant="light" color="gray">
                  {t("roles.builtin.badge")}
                </Badge>
              )}
              <Text size="xs" c="dimmed">
                {t("roles.members", { count: r.members })}
              </Text>
            </Group>
            {!r.builtin && (
              <Group gap={2} wrap="nowrap">
                <Tooltip label={t("roles.rename")}>
                  <ActionIcon variant="subtle" onClick={() => setNaming(r)} aria-label={t("roles.rename")}>
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
                    <Stack gap="xs" maw={260}>
                      <Text size="sm">{t("roles.deleteConfirm", { count: r.members })}</Text>
                      <Button size="xs" color="red" loading={remove.isPending} onClick={() => remove.mutate(r.id)}>
                        {t("finance.action.delete")}
                      </Button>
                    </Stack>
                  </Popover.Dropdown>
                </Popover>
              </Group>
            )}
          </Group>
          <GrantList grants={r.grants} owner={{ group_id: r.id }} emptyKey="roles.noGrants" onChanged={refresh} />
        </Paper>
      ))}
      {naming && (
        <RoleName
          role={naming === "new" ? null : naming}
          onClose={() => setNaming(null)}
          onSaved={() => {
            setNaming(null);
            refresh();
          }}
        />
      )}
    </Stack>
  );
}

function RoleName(props: { role: Role | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(props.role?.name ?? "");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => (props.role ? accessApi.renameRole(props.role.id, name) : accessApi.createRole(name)),
    onSuccess: props.onSaved,
    onError: (err) => setError(problemText(t, err)),
  });
  return (
    <Modal opened onClose={props.onClose} title={t(props.role ? "roles.rename" : "roles.add")}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) save.mutate();
        }}
      >
        <Stack gap="sm">
          <TextInput label={t("roles.name")} description={t("roles.nameHint")} value={name} onChange={(e) => setName(e.currentTarget.value)} data-autofocus required />
          {error && <Alert color="red">{error}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={props.onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={save.isPending} disabled={!name.trim()}>
              {t("finance.action.save")}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
