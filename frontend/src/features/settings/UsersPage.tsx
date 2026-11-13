/**
 * Settings → Accounts (admins): who can log in, their roles and own person,
 * on/off, and their access exceptions. A new account gets a one-time link
 * (copy it, send it) to set its password; the same button makes a reset link
 * for a forgotten password.
 */
import { useState } from "react";
import {
  ActionIcon,
  Alert,
  Avatar,
  Badge,
  Button,
  Divider,
  Group,
  Modal,
  MultiSelect,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconLink, IconPencil, IconPlus } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/PageHeader";
import { useMe } from "@/features/auth/useMe";
import { peopleApi } from "@/features/people/api";
import { fmtDate, fmtDateTime } from "@/lib/format";

import { type Account, accessApi, type Locale, type NewLink, problemText, usersApi } from "./api";
import { GrantList } from "./GrantList";
import { LinkBox, roleLabel, SettingsNav } from "./parts";

const NEW = "__new";
const NONE = "__none";

export function UsersPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const [form, setForm] = useState<Account | "new" | null>(null);
  const [shown, setShown] = useState<{ link: NewLink; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["users"] });
    void qc.invalidateQueries({ queryKey: ["people"] });
    void qc.invalidateQueries({ queryKey: ["access"] });
  };
  const newLink = useMutation({
    mutationFn: (u: Account) => usersApi.newLink(u.id).then((link) => ({ link, name: u.name || u.email })),
    onSuccess: (r) => {
      setShown(r);
      refresh();
    },
    onError: (err) => setError(problemText(t, err)),
  });

  return (
    <Stack gap="lg">
      <PageHeader
        title={t("settings.section.users")}
        subtitle={t("users.subtitle")}
        actions={
          <>
            <SettingsNav />
            <Button leftSection={<IconPlus size={16} />} onClick={() => setForm("new")}>
              {t("users.add")}
            </Button>
          </>
        }
      />
      {error && (
        <Alert color="red" withCloseButton onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      <Paper withBorder p="md">
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("users.f.account")}</Table.Th>
              <Table.Th visibleFrom="sm">{t("users.f.roles")}</Table.Th>
              <Table.Th visibleFrom="sm">{t("users.f.status")}</Table.Th>
              <Table.Th visibleFrom="sm">{t("users.f.lastLogin")}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(users.data ?? []).map((u) => (
              <Table.Tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.55 }}>
                <Table.Td>
                  <Group gap="sm" wrap="nowrap">
                    <Avatar color={u.person?.color ?? "gray"} variant="filled" radius="xl" size="md">
                      {(u.name || u.email).slice(0, 2).toUpperCase()}
                    </Avatar>
                    <div style={{ minWidth: 0 }}>
                      <Text fw={600} size="sm">
                        {u.name || u.email}
                      </Text>
                      <Text size="xs" c="dimmed" style={{ overflowWrap: "anywhere" }}>
                        {u.email}
                      </Text>
                      {/* Phones: roles and status under the name. */}
                      <Group gap={4} mt={4} hiddenFrom="sm">
                        <Roles u={u} />
                        <Status u={u} />
                      </Group>
                    </div>
                  </Group>
                </Table.Td>
                <Table.Td visibleFrom="sm">
                  <Group gap={4}>
                    <Roles u={u} />
                  </Group>
                </Table.Td>
                <Table.Td visibleFrom="sm">
                  <Status u={u} />
                </Table.Td>
                <Table.Td visibleFrom="sm">
                  <Text size="sm" c="dimmed">
                    {u.last_login ? fmtDateTime(u.last_login) : "—"}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={2} justify="flex-end" wrap="nowrap">
                    {u.is_active && (
                      <Tooltip label={t(u.has_password ? "users.resetLink" : "users.inviteLink")}>
                        <ActionIcon
                          variant="subtle"
                          loading={newLink.isPending && newLink.variables?.id === u.id}
                          onClick={() => newLink.mutate(u)}
                          aria-label={t(u.has_password ? "users.resetLink" : "users.inviteLink")}
                        >
                          <IconLink size={16} />
                        </ActionIcon>
                      </Tooltip>
                    )}
                    <Tooltip label={t("finance.action.edit")}>
                      <ActionIcon variant="subtle" onClick={() => setForm(u)} aria-label={t("finance.action.edit")}>
                        <IconPencil size={16} />
                      </ActionIcon>
                    </Tooltip>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Text size="xs" c="dimmed" mt="sm">
          {t("users.linkHint")}
        </Text>
      </Paper>

      {form && (
        <AccountForm
          account={form === "new" ? null : form}
          onClose={() => setForm(null)}
          onCreated={(link, name) => {
            setForm(null);
            setShown({ link, name });
            refresh();
          }}
          onSaved={() => {
            setForm(null);
            refresh();
          }}
          onChanged={refresh}
        />
      )}
      <Modal opened={!!shown} onClose={() => setShown(null)} title={t("users.link.modalTitle")} size="lg">
        {shown && <LinkBox link={shown.link} name={shown.name} />}
      </Modal>
    </Stack>
  );
}

function Roles({ u }: { u: Account }) {
  const { t } = useTranslation();
  return (
    <>
      {u.is_main_admin && (
        <Badge size="sm" color="grape" variant="light">
          {t("users.mainAdmin")}
        </Badge>
      )}
      {u.roles.map((r) => (
        <Badge key={r.id} size="sm" variant="light">
          {roleLabel(r.name, t)}
        </Badge>
      ))}
    </>
  );
}

function Status({ u }: { u: Account }) {
  const { t } = useTranslation();
  if (!u.is_active) {
    return (
      <Badge size="sm" color="gray" variant="outline">
        {t("users.status.off")}
      </Badge>
    );
  }
  if (u.open_link) {
    return (
      <Tooltip label={t("users.status.linkUntil", { date: fmtDate(u.open_link.expires_at.slice(0, 10)) })}>
        <Badge size="sm" color="orange" variant="light">
          {t(`users.status.${u.open_link.purpose}`)}
        </Badge>
      </Tooltip>
    );
  }
  if (!u.has_password) {
    return (
      <Badge size="sm" color="orange" variant="outline">
        {t("users.status.noPassword")}
      </Badge>
    );
  }
  return (
    <Badge size="sm" color="teal" variant="light">
      {t("users.status.active")}
    </Badge>
  );
}

function AccountForm(props: {
  account: Account | null;
  onClose: () => void;
  onCreated: (link: NewLink, name: string) => void;
  onSaved: () => void;
  onChanged: () => void;
}) {
  const { t, i18n } = useTranslation();
  const me = useMe().data;
  const a = props.account;
  const roles = useQuery({ queryKey: ["access", "roles"], queryFn: accessApi.roles });
  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const grants = useQuery({
    queryKey: ["access", "grants", a?.id],
    queryFn: () => accessApi.userGrants(a!.id),
    enabled: !!a,
  });
  const [name, setName] = useState(a?.name ?? "");
  const [email, setEmail] = useState(a?.email ?? "");
  const [locale, setLocale] = useState<Locale>(a?.locale ?? (i18n.language.startsWith("pl") ? "pl" : "en"));
  const [roleIds, setRoleIds] = useState<string[]>((a?.roles ?? []).map((r) => String(r.id)));
  const [person, setPerson] = useState<string>(a ? (a.person?.id ?? NONE) : NEW);
  const [active, setActive] = useState(a?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  // Someone's own person: one without an account yet (or this account's).
  const personOptions = [
    ...(a ? [] : [{ value: NEW, label: t("users.f.newPerson") }]),
    { value: NONE, label: t("users.f.noPerson") },
    ...(people.data ?? [])
      .filter((p) => !p.has_login || p.id === a?.person?.id)
      .map((p) => ({ value: p.id, label: p.display_name })),
  ];
  const save = useMutation({
    mutationFn: async () => {
      const body = {
        email,
        name,
        locale,
        role_ids: roleIds.map(Number),
        person_id: person === NEW || person === NONE ? null : person,
      };
      if (a) {
        await usersApi.update(a.id, { ...body, is_active: active });
        props.onSaved();
      } else {
        const created = await usersApi.create({ ...body, new_person: person === NEW });
        props.onCreated(created.link, created.user.name || created.user.email);
      }
    },
    onError: (err) => setError(problemText(t, err)),
  });
  const self = a?.id === me?.id;

  return (
    <Modal opened onClose={props.onClose} title={t(a ? "users.editTitle" : "users.addTitle")} size="lg">
      <Stack gap="sm">
        <Group grow align="flex-start" wrap="wrap">
          <TextInput label={t("users.f.name")} value={name} onChange={(e) => setName(e.currentTarget.value)} miw={200} required />
          <TextInput label={t("auth.email")} type="email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} miw={200} required />
        </Group>
        <MultiSelect
          label={t("users.f.roles")}
          description={t("users.f.rolesHint")}
          data={(roles.data ?? []).map((r) => ({ value: String(r.id), label: roleLabel(r.name, t) }))}
          value={roleIds}
          onChange={setRoleIds}
          disabled={a?.is_main_admin && !self}
        />
        <Group grow align="flex-start" wrap="wrap">
          <Select
            label={t("users.f.person")}
            description={t("users.f.personHint")}
            data={personOptions}
            value={person}
            onChange={(v) => v && setPerson(v)}
            allowDeselect={false}
            miw={200}
          />
          <Select
            label={t("users.f.locale")}
            data={[
              { value: "pl", label: "Polski" },
              { value: "en", label: "English" },
            ]}
            value={locale}
            onChange={(v) => v && setLocale(v as Locale)}
            allowDeselect={false}
            miw={140}
          />
        </Group>
        {a && (
          <Switch
            label={t("users.f.active")}
            description={t(self ? "users.f.activeSelf" : "users.f.activeHint")}
            checked={active}
            onChange={(e) => setActive(e.currentTarget.checked)}
            disabled={self}
          />
        )}
        {a?.is_main_admin && (
          <Text size="xs" c="dimmed">
            {t("users.mainAdminHint")}
          </Text>
        )}
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={props.onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            loading={save.isPending}
            disabled={!name.trim() || !email.trim()}
            onClick={() => {
              setError(null);
              save.mutate();
            }}
          >
            {t(a ? "finance.action.save" : "users.create")}
          </Button>
        </Group>

        {a && !a.is_main_admin && (
          <>
            <Divider my="xs" />
            <Title order={6}>{t("users.exceptions")}</Title>
            <Text size="xs" c="dimmed">
              {t("users.exceptionsHint")}
            </Text>
            <GrantList
              grants={grants.data ?? []}
              owner={{ user_id: a.id }}
              emptyKey="users.noExceptions"
              onChanged={() => {
                void grants.refetch();
                props.onChanged();
              }}
            />
          </>
        )}
      </Stack>
    </Modal>
  );
}
