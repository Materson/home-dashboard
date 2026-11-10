import { useState } from "react";
import { Alert, Button, Container, Paper, PasswordInput, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

export function LoginPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const form = useForm({
    initialValues: { email: "", password: "" },
    validate: {
      email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : t("auth.email")),
      password: (v) => (v.length >= 1 ? null : t("auth.password")),
    },
  });

  async function submit(values: typeof form.values) {
    setError(null);
    // Make sure the csrftoken cookie exists before the login POST.
    await fetch("/api/csrf", { credentials: "include" });
    const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
    const resp = await fetch("/api/_allauth/browser/v1/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(values),
    });
    if (!resp.ok) {
      setError(t("auth.loginFailed"));
      return;
    }
    await qc.invalidateQueries();
  }

  return (
    <Container size={420} my={80}>
      <Title ta="center" order={2}>
        {t("app.title")}
      </Title>
      <Paper withBorder shadow="sm" p="lg" mt="lg" radius="md">
        <form onSubmit={form.onSubmit(submit)}>
          <TextInput label={t("auth.email")} required {...form.getInputProps("email")} />
          <PasswordInput mt="md" label={t("auth.password")} required {...form.getInputProps("password")} />
          {error && (
            <Alert color="red" mt="md">
              {error}
            </Alert>
          )}
          <Button fullWidth mt="xl" type="submit">
            {t("auth.login")}
          </Button>
        </form>
      </Paper>
    </Container>
  );
}
