/**
 * Opening a one-time link: someone sets the password of the account an
 * admin made for them (or a new one after "forgot password"), then is in.
 */
import { useState } from "react";
import { Alert, Box, Button, Loader, Paper, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconKey } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { problemText, setupApi } from "./api";
import { type NewPassword, PasswordFields, passwordIssue } from "./parts";

export function InvitePage() {
  const { t } = useTranslation();
  const { token = "" } = useParams();
  const info = useQuery({ queryKey: ["invite", token], queryFn: () => setupApi.linkInfo(token), retry: false });
  const [password, setPassword] = useState<NewPassword>({ password: "", repeat: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      await setupApi.acceptLink(token, password.password);
      // Logged in as them now: a fresh start (nobody else's data cached).
      window.location.assign("/");
    } catch (err) {
      setError(problemText(t, err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box
      mih="100dvh"
      p="md"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))",
      }}
    >
      <Paper withBorder shadow="lg" p="xl" w="100%" maw={420}>
        <Stack align="center" gap={6} mb="lg">
          <ThemeIcon size={52} radius="lg" variant="gradient" gradient={{ from: "indigo.5", to: "violet.5", deg: 135 }}>
            <IconKey size={28} stroke={1.7} />
          </ThemeIcon>
        </Stack>
        {info.isLoading ? (
          <Stack align="center">
            <Loader size="sm" />
          </Stack>
        ) : !info.data ? (
          <Stack gap="xs" align="center">
            <Title order={4}>{t("invite.invalidTitle")}</Title>
            <Text size="sm" c="dimmed" ta="center">
              {t("invite.invalid")}
            </Text>
          </Stack>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!passwordIssue(password)) void submit();
            }}
          >
            <Stack gap="sm">
              <Title order={4} ta="center">
                {t(info.data.purpose === "invite" ? "invite.welcome" : "invite.resetTitle", { name: info.data.name })}
              </Title>
              <Text size="sm" c="dimmed" ta="center">
                {t(info.data.purpose === "invite" ? "invite.intro" : "invite.resetIntro", { email: info.data.email })}
              </Text>
              <PasswordFields value={password} onChange={setPassword} />
              {error && <Alert color="red">{error}</Alert>}
              <Button type="submit" size="md" mt="sm" loading={busy} disabled={!!passwordIssue(password)}>
                {t("invite.save")}
              </Button>
            </Stack>
          </form>
        )}
      </Paper>
    </Box>
  );
}
