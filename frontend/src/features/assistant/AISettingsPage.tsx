/**
 * Ustawienia → AI (admin): provider profiles (key stored encrypted, never
 * shown back; "Test" checks key + model), which profile chats and which is
 * the local one for private conversations, and per module where its data
 * may go: off / local model only / cloud with aliases.
 */
import { useEffect, useState } from "react";
import {
  ActionIcon,
  Alert,
  Autocomplete,
  Badge,
  Button,
  Group,
  Modal,
  Paper,
  PasswordInput,
  SegmentedControl,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconAlertTriangle,
  IconPencil,
  IconPhoto,
  IconPlugConnected,
  IconPlus,
  IconShieldLock,
  IconTrash,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";

import {
  type AISettings,
  ASSISTANT_KEY,
  assistantApi,
  type OpenRouterModel,
  type Policy,
  type Profile,
  type ProfilePayload,
  type ProviderKind,
} from "./api";

const MODULES = ["finance", "cars", "household", "people", "health", "notes", "documents"] as const;
const KINDS: ProviderKind[] = ["anthropic", "openai", "google", "openrouter", "ollama", "openai_compatible"];
/** Services on the internet: need a key, always "cloud" (the server enforces it too). */
const HOSTED: ProviderKind[] = ["anthropic", "openai", "google", "openrouter"];
const KEY = [...ASSISTANT_KEY, "settings"];

export function AISettingsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: [...ASSISTANT_KEY, "status"], queryFn: assistantApi.status });
  const settings = useQuery({ queryKey: KEY, queryFn: assistantApi.settings, enabled: !!status.data?.can_manage });
  const [editing, setEditing] = useState<Profile | null | "new">(null);
  const [tests, setTests] = useState<Record<string, { ok: boolean; detail: string }>>({});

  const refresh = () => qc.invalidateQueries({ queryKey: ASSISTANT_KEY });
  const save = useMutation({
    mutationFn: (p: Partial<Omit<AISettings, "profiles">>) => assistantApi.saveSettings(p),
    onSuccess: (data) => {
      qc.setQueryData(KEY, data);
      refresh();
    },
  });
  const remove = useMutation({ mutationFn: assistantApi.deleteProfile, onSuccess: refresh });
  const test = useMutation({
    mutationFn: (id: string) => assistantApi.testProfile(id),
    onSuccess: (r, id) => setTests((all) => ({ ...all, [id]: r })),
  });

  if (status.data && !status.data.can_manage) {
    return (
      <Stack>
        <PageHeader title={t("nav.settings")} />
        <Text c="dimmed">{t("settings.nothingForYou")}</Text>
      </Stack>
    );
  }
  const s = settings.data;
  const profiles = s?.profiles ?? [];
  const option = (p: Profile) => ({ value: p.id, label: `${p.name} (${t(`assistant.location.${p.location}`)})` });

  return (
    <Stack gap="lg">
      <PageHeader title={t("settings.ai.title")} subtitle={t("page.settings.subtitle")} />

      <Paper withBorder p="md">
        <Group justify="space-between" mb="sm">
          <Title order={4}>{t("settings.ai.profiles")}</Title>
          <Button size="xs" leftSection={<IconPlus size={14} />} onClick={() => setEditing("new")}>
            {t("settings.ai.addProfile")}
          </Button>
        </Group>
        <Table>
          <Table.Tbody>
            {profiles.map((p) => (
              <Table.Tr key={p.id}>
                <Table.Td>
                  <Text fw={600}>{p.name}</Text>
                  <Text size="xs" c="dimmed">
                    {t(`settings.ai.kind.${p.kind}`)} · {p.model}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    <Badge size="sm" variant="light" color={p.location === "cloud" ? "orange" : "teal"}>
                      {t(`assistant.location.${p.location}`)}
                    </Badge>
                    {!p.enabled && (
                      <Badge size="sm" color="gray">
                        {t("settings.ai.disabled")}
                      </Badge>
                    )}
                    {p.vision && (
                      <Badge size="sm" variant="outline" color="gray">
                        {t("settings.ai.vision")}
                      </Badge>
                    )}
                    {p.kind === "openrouter" && p.allow_data_collection && (
                      <Badge size="sm" variant="outline" color="orange">
                        {t("settings.ai.mayStore")}
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td>
                  {tests[p.id] && (
                    <Text size="xs" c={tests[p.id].ok ? "teal" : "red"}>
                      {tests[p.id].ok ? `✓ ${tests[p.id].detail}` : tests[p.id].detail}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    <Tooltip label={t("settings.ai.test")}>
                      <ActionIcon variant="subtle" loading={test.isPending && test.variables === p.id} onClick={() => test.mutate(p.id)}>
                        <IconPlugConnected size={16} />
                      </ActionIcon>
                    </Tooltip>
                    <ActionIcon variant="subtle" onClick={() => setEditing(p)} aria-label={t("finance.action.edit")}>
                      <IconPencil size={16} />
                    </ActionIcon>
                    <ActionIcon variant="subtle" color="red" onClick={() => remove.mutate(p.id)} aria-label={t("finance.action.delete")}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
            {settings.isSuccess && !profiles.length && (
              <Table.Tr>
                <Table.Td c="dimmed">{t("settings.ai.noProfiles")}</Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      {s && (
        <Paper withBorder p="md">
          <Title order={4} mb="sm">
            {t("settings.ai.use")}
          </Title>
          <Group grow align="flex-start">
            <Select
              label={t("settings.ai.chatProfile")}
              description={t("settings.ai.chatProfileHint")}
              clearable
              data={profiles.filter((p) => p.enabled).map(option)}
              value={s.chat_profile_id}
              onChange={(v) => save.mutate({ chat_profile_id: v })}
            />
            <Select
              label={t("settings.ai.localProfile")}
              description={t("settings.ai.localProfileHint")}
              clearable
              data={profiles.filter((p) => p.enabled && p.location === "local").map(option)}
              value={s.local_profile_id}
              onChange={(v) => save.mutate({ local_profile_id: v })}
            />
          </Group>
        </Paper>
      )}

      {s && (
        <Paper withBorder p="md">
          <Title order={4}>{t("settings.ai.privacy")}</Title>
          <Text size="sm" c="dimmed" mb="sm">
            {t("settings.ai.privacyHint")}
          </Text>
          <Stack gap="xs">
            {MODULES.map((m) => (
              <Group key={m} justify="space-between" wrap="nowrap">
                <Stack gap={0}>
                  <Text size="sm" fw={500}>
                    {t(`assistant.module.${m}`)}
                  </Text>
                  {m === "documents" && (
                    <Text size="xs" c="dimmed">
                      {t("settings.ai.documentsHint")}
                    </Text>
                  )}
                </Stack>
                <SegmentedControl
                  size="xs"
                  value={s.policies[m] ?? "off"}
                  onChange={(v) => save.mutate({ policies: { [m]: v as Policy } })}
                  data={(["off", "local", "cloud"] as Policy[]).map((v) => ({ value: v, label: t(`settings.ai.policy.${v}`) }))}
                />
              </Group>
            ))}
          </Stack>
          {save.isError && (
            <Alert color="red" mt="sm">
              {(save.error as Error).message}
            </Alert>
          )}
        </Paper>
      )}

      <ProfileModal profile={editing} onClose={() => setEditing(null)} onSaved={refresh} />
    </Stack>
  );
}

function ProfileModal(props: { profile: Profile | null | "new"; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const editing = props.profile && props.profile !== "new" ? props.profile : null;
  const blank: ProfilePayload = {
    name: "",
    kind: "anthropic",
    model: "claude-opus-5-5",
    base_url: "",
    api_key: "",
    location: "cloud",
    vision: true,
    allow_data_collection: false,
    enabled: true,
  };
  const [form, setForm] = useState<ProfilePayload>(blank);
  useEffect(() => {
    if (props.profile === null) return;
    setForm(editing ? { ...editing, api_key: "" } : blank);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset on open
  }, [props.profile]);
  const set = <K extends keyof ProfilePayload>(k: K, v: ProfilePayload[K]) => setForm((f) => ({ ...f, [k]: v }));
  const save = useMutation({
    mutationFn: () => assistantApi.saveProfile(form, editing?.id),
    onSuccess: () => {
      props.onSaved();
      props.onClose();
    },
  });
  const needsUrl = form.kind === "ollama" || form.kind === "openai_compatible";
  const hosted = HOSTED.includes(form.kind);

  return (
    <Modal opened={props.profile !== null} onClose={props.onClose} title={t(editing ? "settings.ai.editProfile" : "settings.ai.addProfile")}>
      <Stack>
        <TextInput label={t("settings.ai.f.name")} required value={form.name} onChange={(e) => set("name", e.currentTarget.value)} />
        <Select
          label={t("settings.ai.f.kind")}
          allowDeselect={false}
          data={KINDS.map((k) => ({ value: k, label: t(`settings.ai.kind.${k}`) }))}
          value={form.kind}
          onChange={(v) => {
            const kind = (v ?? "anthropic") as ProviderKind;
            setForm((f) => ({
              ...f,
              kind,
              location: HOSTED.includes(kind) ? "cloud" : kind === "ollama" ? "local" : f.location,
              model:
                kind === "anthropic" && !f.model
                  ? "claude-opus-5-5"
                  : kind === "openrouter" && !f.model.includes("/")
                    ? "" // OpenRouter ids are "provider/model": pick one from its list
                    : f.model,
            }));
          }}
        />
        {form.kind === "openrouter" ? (
          <OpenRouterModelInput
            value={form.model}
            onChange={(v) => set("model", v)}
            onPick={(m) => set("vision", m.vision)}
            profileId={editing?.id}
          />
        ) : (
          <TextInput
            label={t("settings.ai.f.model")}
            description={t(`settings.ai.modelHint.${form.kind}`)}
            required
            value={form.model}
            onChange={(e) => set("model", e.currentTarget.value)}
          />
        )}
        {form.kind === "openrouter" && (
          <>
            <Switch
              label={t("settings.ai.f.allowDataCollection")}
              description={t("settings.ai.f.allowDataCollectionHint")}
              checked={form.allow_data_collection}
              onChange={(e) => set("allow_data_collection", e.currentTarget.checked)}
            />
            {form.allow_data_collection ? (
              <Alert variant="light" color="orange" icon={<IconAlertTriangle size={18} />} p="xs">
                <Text size="xs">{t("settings.ai.openrouter.mayStore")}</Text>
              </Alert>
            ) : (
              <Alert variant="light" color="teal" icon={<IconShieldLock size={18} />} p="xs">
                <Text size="xs">{t("settings.ai.openrouter.privacy")}</Text>
                {form.model.endsWith(":free") && (
                  <Text size="xs" c="orange" mt={4}>
                    {t("settings.ai.openrouter.freeNeedsSwitch")}
                  </Text>
                )}
              </Alert>
            )}
          </>
        )}
        {needsUrl && (
          <TextInput
            label={t("settings.ai.f.baseUrl")}
            placeholder="http://192.168.1.10:11434/v1"
            value={form.base_url}
            onChange={(e) => set("base_url", e.currentTarget.value)}
          />
        )}
        <PasswordInput
          label={t("settings.ai.f.apiKey")}
          description={editing?.has_key ? t("settings.ai.f.apiKeyKeep") : hosted ? undefined : t("settings.ai.f.apiKeyOptional")}
          required={hosted && !editing?.has_key}
          value={form.api_key}
          onChange={(e) => set("api_key", e.currentTarget.value)}
          autoComplete="new-password"
        />
        <SegmentedControl
          value={hosted ? "cloud" : form.location}
          onChange={(v) => set("location", v as ProfilePayload["location"])}
          disabled={hosted}
          data={[
            { value: "cloud", label: t("assistant.location.cloud") },
            { value: "local", label: t("assistant.location.local") },
          ]}
        />
        <Text size="xs" c="dimmed">
          {t(hosted ? "settings.ai.f.cloudOnly" : "settings.ai.f.locationHint")}
        </Text>
        <Switch label={t("settings.ai.f.vision")} checked={form.vision} onChange={(e) => set("vision", e.currentTarget.checked)} />
        <Switch label={t("settings.ai.f.enabled")} checked={form.enabled} onChange={(e) => set("enabled", e.currentTarget.checked)} />
        {save.isError && <Alert color="red">{(save.error as Error).message}</Alert>}
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!form.name.trim() || !form.model.trim()}>
          {t("finance.action.save")}
        </Button>
      </Stack>
    </Modal>
  );
}

/** OpenRouter's model id, picked from its list of models that can use the
 *  assistant's tools (with price and photo support); typing works too. */
function OpenRouterModelInput(props: {
  value: string;
  onChange: (id: string) => void;
  onPick: (model: OpenRouterModel) => void;
  profileId?: string;
}) {
  const { t } = useTranslation();
  const models = useQuery({
    queryKey: [...ASSISTANT_KEY, "openrouter-models", props.profileId ?? ""],
    queryFn: () => assistantApi.openrouterModels(props.profileId),
    staleTime: 3_600_000,
    retry: false,
  });
  const byId = new Map((models.data ?? []).map((m) => [m.id, m]));
  return (
    <Autocomplete
      label={t("settings.ai.f.model")}
      description={t(models.isError ? "settings.ai.openrouter.modelsError" : "settings.ai.modelHint.openrouter")}
      placeholder="anthropic/claude-opus-4.5"
      required
      data={(models.data ?? []).map((m) => m.id)}
      limit={50}
      maxDropdownHeight={320}
      value={props.value}
      onChange={props.onChange}
      onOptionSubmit={(id) => {
        const m = byId.get(id);
        if (m) props.onPick(m);
      }}
      renderOption={({ option }) => {
        const m = byId.get(option.value);
        return (
          <Stack gap={0}>
            <Group gap={6} wrap="nowrap">
              <Text size="sm">{option.value}</Text>
              {m?.vision && <IconPhoto size={14} color="var(--mantine-color-dimmed)" aria-label={t("settings.ai.f.vision")} />}
            </Group>
            {m?.price_in != null && (
              <Text size="xs" c="dimmed">
                {t("settings.ai.openrouter.price", { in: m.price_in, out: m.price_out ?? "?" })}
              </Text>
            )}
          </Stack>
        );
      }}
    />
  );
}
