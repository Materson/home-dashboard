/**
 * First-time setup, step 2: the family. Each member is a person (health,
 * finance "for whom" …); a member who'll log in also gets an account with a
 * role and a one-time link to set their password. Everything here can be
 * changed later in People and Settings → Accounts.
 */
import { useState } from "react";
import { Avatar, Badge, Button, Group, Paper, Select, Stack, Switch, Text, TextInput, Title } from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { IconArrowRight, IconPlus } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { peopleApi } from "@/features/people/api";
import { isoDate } from "@/lib/format";

import { accessApi, type Locale, type NewLink, problemText, usersApi } from "./api";
import { LinkBox, roleLabel } from "./parts";

const COLORS = ["#be4bdb", "#228be6", "#40c057", "#fd7e14", "#e64980", "#15aabf", "#fab005", "#7950f2"];

type Member = { id: string; name: string; color: string; email?: string; role?: string; link?: NewLink };

export function FamilyStep() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const roles = useQuery({ queryKey: ["access", "roles"], queryFn: accessApi.roles });
  const [added, setAdded] = useState<Member[]>([]);
  const [name, setName] = useState("");
  const [birth, setBirth] = useState<Date | null>(null);
  const [login, setLogin] = useState(false);
  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const roleOptions = (roles.data ?? []).map((r) => ({ value: String(r.id), label: roleLabel(r.name, t) }));
  const defaultRole = roles.data?.find((r) => r.name === "Parent")?.id;
  const ready = name.trim() && (!login || (email.trim() && (roleId ?? defaultRole)));

  async function add() {
    setError(null);
    setBusy(true);
    try {
      const color = COLORS[((people.data?.length ?? 0) + added.length) % COLORS.length];
      const person = await peopleApi.save({ display_name: name.trim(), birth_date: birth ? isoDate(birth) : null, color });
      const member: Member = { id: person.id, name: person.display_name, color };
      if (login) {
        const role = Number(roleId ?? defaultRole);
        const locale: Locale = i18n.language.startsWith("pl") ? "pl" : "en";
        const created = await usersApi.create({ email, name: person.display_name, locale, role_ids: [role], person_id: person.id });
        member.email = created.user.email;
        member.role = roleOptions.find((o) => o.value === String(role))?.label;
        member.link = created.link;
      }
      setAdded([...added, member]);
      setName("");
      setBirth(null);
      setEmail("");
      setLogin(false);
      void qc.invalidateQueries({ queryKey: ["people"] });
    } catch (err) {
      setError(problemText(t, err));
    } finally {
      setBusy(false);
    }
  }

  const addedIds = new Set(added.map((m) => m.id));
  const before = (people.data ?? []).filter((p) => !addedIds.has(p.id));

  return (
    <Stack gap="lg" maw={720}>
      <PageHeader title={t("setup.family.title")} subtitle={t("setup.family.subtitle")} />

      <Paper withBorder p="md">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) void add();
          }}
        >
          <Stack gap="sm">
            <Group grow align="flex-start" wrap="wrap">
              <TextInput label={t("setup.family.name")} required value={name} onChange={(e) => setName(e.currentTarget.value)} miw={200} />
              <DatePickerInput
                label={t("setup.family.birth")}
                description={t("setup.family.birthHint")}
                value={birth}
                onChange={setBirth}
                valueFormat="DD.MM.YYYY"
                clearable
                maxDate={new Date()}
                miw={200}
              />
            </Group>
            <Switch label={t("setup.family.login")} description={t("setup.family.loginHint")} checked={login} onChange={(e) => setLogin(e.currentTarget.checked)} />
            {login && (
              <Group grow align="flex-start" wrap="wrap">
                <TextInput label={t("auth.email")} type="email" required value={email} onChange={(e) => setEmail(e.currentTarget.value)} miw={200} />
                <Select
                  label={t("users.f.role")}
                  data={roleOptions}
                  value={roleId ?? (defaultRole ? String(defaultRole) : null)}
                  onChange={setRoleId}
                  allowDeselect={false}
                  miw={200}
                />
              </Group>
            )}
            {error && <Text c="red" size="sm">{error}</Text>}
            <Group justify="flex-end">
              <Button type="submit" leftSection={<IconPlus size={16} />} loading={busy} disabled={!ready}>
                {t("setup.family.add")}
              </Button>
            </Group>
          </Stack>
        </form>
      </Paper>

      <Stack gap="sm">
        <Title order={5}>{t("setup.family.members")}</Title>
        {before.map((p) => (
          <Group key={p.id} gap="sm">
            <Avatar color={p.color} variant="filled" radius="xl">
              {p.display_name.slice(0, 2).toUpperCase()}
            </Avatar>
            <Text fw={500}>{p.display_name}</Text>
            {p.has_login && (
              <Badge size="xs" variant="light">
                {t("people.hasLogin")}
              </Badge>
            )}
          </Group>
        ))}
        {added.map((m) => (
          <Stack key={m.id} gap={6}>
            <Group gap="sm">
              <Avatar color={m.color} variant="filled" radius="xl">
                {m.name.slice(0, 2).toUpperCase()}
              </Avatar>
              <Text fw={500}>{m.name}</Text>
              {m.role && (
                <Badge size="xs" variant="light">
                  {m.role}
                </Badge>
              )}
              {m.email && (
                <Text size="xs" c="dimmed">
                  {m.email}
                </Text>
              )}
            </Group>
            {m.link && <LinkBox link={m.link} name={m.name} />}
          </Stack>
        ))}
      </Stack>

      <Group justify="flex-end">
        <Button variant="light" rightSection={<IconArrowRight size={16} />} onClick={() => navigate("/")}>
          {t("setup.family.done")}
        </Button>
      </Group>
    </Stack>
  );
}
