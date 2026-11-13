/**
 * First-time setup on a fresh install (no account yet — e.g. right after
 * moving to the NAS): the first account, with full admin rights. Then the
 * family step (FamilyStep) adds the family and their logins.
 */
import { useState } from "react";
import { Alert, Box, Button, Paper, SegmentedControl, Stack, Text, TextInput, ThemeIcon, Title } from "@mantine/core";
import { IconHomeHeart } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";

import { type Locale, problemText, setupApi } from "./api";
import { type NewPassword, PasswordFields, passwordIssue } from "./parts";

export function SetupPage() {
  const { t, i18n } = useTranslation();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState<NewPassword>({ password: "", repeat: "" });
  const [locale, setLocale] = useState<Locale>(i18n.language.startsWith("pl") ? "pl" : "en");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ready = name.trim() && email.trim() && !passwordIssue(password);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      await setupApi.run({ name, email, password: password.password, locale });
      // Logged in now: a fresh start of the app, at the family step.
      window.location.assign("/setup/family");
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
      <Paper withBorder shadow="lg" p="xl" w="100%" maw={440}>
        <Stack align="center" gap={6} mb="lg">
          <ThemeIcon size={52} radius="lg" variant="gradient" gradient={{ from: "indigo.5", to: "violet.5", deg: 135 }}>
            <IconHomeHeart size={30} stroke={1.7} />
          </ThemeIcon>
          <Title order={3} mt="xs">
            {t("setup.title")}
          </Title>
          <Text size="sm" c="dimmed" ta="center">
            {t("setup.intro")}
          </Text>
        </Stack>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) void submit();
          }}
        >
          <Stack gap="sm">
            <SegmentedControl
              fullWidth
              value={locale}
              onChange={(v) => {
                setLocale(v as Locale);
                void i18n.changeLanguage(v);
                try {
                  localStorage.setItem("lang", v); // kept after setup reloads the app
                } catch {
                  // storage blocked: the browser's language next time
                }
              }}
              data={[
                { value: "pl", label: "Polski" },
                { value: "en", label: "English" },
              ]}
            />
            <TextInput
              label={t("setup.name")}
              description={t("setup.nameHint")}
              required
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
              data-autofocus
            />
            <TextInput
              label={t("auth.email")}
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.currentTarget.value)}
            />
            <PasswordFields value={password} onChange={setPassword} label={t("auth.password")} />
            {error && <Alert color="red">{error}</Alert>}
            <Button type="submit" size="md" mt="sm" loading={busy} disabled={!ready}>
              {t("setup.create")}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Box>
  );
}
