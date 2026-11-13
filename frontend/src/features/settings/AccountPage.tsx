/**
 * Settings → My account (everyone): who I'm logged in as, and changing my
 * password. A forgotten password: an admin makes a reset link (Accounts).
 */
import { useState } from "react";
import { Alert, Button, Group, Paper, PasswordInput, Stack, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useTranslation } from "react-i18next";

import { PageHeader } from "@/components/PageHeader";
import { useMe } from "@/features/auth/useMe";

import { changePassword, problemText } from "./api";
import { type NewPassword, PasswordFields, passwordIssue, SettingsNav } from "./parts";

export function AccountPage() {
  const { t } = useTranslation();
  const me = useMe().data;
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState<NewPassword>({ password: "", repeat: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      await changePassword(current, next.password);
      setCurrent("");
      setNext({ password: "", repeat: "" });
      notifications.show({ color: "teal", message: t("account.passwordChanged") });
    } catch (err) {
      setError(problemText(t, err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Stack gap="lg">
      <PageHeader title={t("settings.section.account")} subtitle={me?.email} actions={<SettingsNav />} />
      <Paper withBorder p="md" maw={520}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (current && !passwordIssue(next)) void submit();
          }}
        >
          <Stack gap="sm">
            <Title order={5}>{t("account.changePassword")}</Title>
            <PasswordInput
              label={t("account.currentPassword")}
              autoComplete="current-password"
              required
              value={current}
              onChange={(e) => setCurrent(e.currentTarget.value)}
            />
            <PasswordFields value={next} onChange={setNext} />
            {error && <Alert color="red">{error}</Alert>}
            <Group justify="flex-end">
              <Button type="submit" loading={busy} disabled={!current || !!passwordIssue(next)}>
                {t("account.savePassword")}
              </Button>
            </Group>
            <Text size="xs" c="dimmed">
              {t("account.forgotHint")}
            </Text>
          </Stack>
        </form>
      </Paper>
    </Stack>
  );
}
