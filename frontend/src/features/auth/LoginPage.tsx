import { useState } from "react";
import { Alert, Box, Button, Paper, PasswordInput, Stack, Text, TextInput, ThemeIcon, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { IconHomeHeart } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

/** What allauth's answer means for the person logging in. */
const LOGIN_ERRORS: Record<number, string> = {
  400: "auth.loginFailed", // wrong email or password
  401: "auth.extraStep", // a pending step (email verification, 2FA code) this page doesn't do
  429: "auth.tooMany", // too many failed attempts
};

export function LoginPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: {
      email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : t("auth.email")),
      password: (v) => (v.length >= 1 ? null : t("auth.password")),
    },
  });

  async function submit(values: typeof form.values) {
    setError(null);
    setBusy(true);
    try {
      // Make sure the csrftoken cookie exists before the login POST.
      await fetch("/api/csrf", { credentials: "include" });
      const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
      const resp = await fetch("/api/_allauth/browser/v1/auth/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify(values),
      });
      // 409: already logged in (e.g. through the admin) — just go on.
      if (!resp.ok && resp.status !== 409) {
        setError(t(LOGIN_ERRORS[resp.status] ?? "auth.unreachable"));
        return;
      }
      await qc.invalidateQueries();
    } catch {
      setError(t("auth.unreachable"));
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
      <Paper withBorder shadow="lg" p="xl" w="100%" maw={400}>
        <Stack align="center" gap={6} mb="xl">
          <ThemeIcon size={52} radius="lg" variant="gradient" gradient={{ from: "indigo.5", to: "violet.5", deg: 135 }}>
            <IconHomeHeart size={30} stroke={1.7} />
          </ThemeIcon>
          <Title order={3} mt="xs">
            {t("app.title")}
          </Title>
          <Text size="sm" c="dimmed">
            {t("auth.welcome")}
          </Text>
        </Stack>
        <form onSubmit={form.onSubmit(submit)}>
          <TextInput label={t("auth.email")} required autoComplete="username" {...form.getInputProps("email")} />
          <PasswordInput mt="md" label={t("auth.password")} required autoComplete="current-password" {...form.getInputProps("password")} />
          {error && (
            <Alert color="red" mt="md">
              {error}
            </Alert>
          )}
          <Button fullWidth mt="xl" size="md" type="submit" loading={busy}>
            {t("auth.login")}
          </Button>
          <Text size="xs" c="dimmed" ta="center" mt="md">
            {t("auth.forgot")}
          </Text>
        </form>
      </Paper>
    </Box>
  );
}
