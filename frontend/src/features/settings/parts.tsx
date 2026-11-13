/**
 * Small pieces the setup, invite and settings screens share: a new password
 * typed twice, the one-time link box, and the switch between settings sections.
 */
import { ActionIcon, Alert, CopyButton, Group, PasswordInput, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy, IconLink } from "@tabler/icons-react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { ChoiceTabs } from "@/components/ChoiceTabs";
import { usePermissions } from "@/features/auth/usePermissions";
import { fmtDateTime } from "@/lib/format";

import { linkUrl, type NewLink } from "./api";

export const MIN_PASSWORD = 10; // as the backend's MinimumLengthValidator

export type NewPassword = { password: string; repeat: string };

/** Why a new password can't be sent yet (null: it can). */
export function passwordIssue(p: NewPassword): "short" | "repeat" | null {
  if (p.password.length < MIN_PASSWORD) return "short";
  if (p.password !== p.repeat) return "repeat";
  return null;
}

export function PasswordFields(props: { value: NewPassword; onChange: (v: NewPassword) => void; label?: string }) {
  const { t } = useTranslation();
  const issue = passwordIssue(props.value);
  return (
    <>
      <PasswordInput
        label={props.label ?? t("account.newPassword")}
        description={t("account.passwordRule", { count: MIN_PASSWORD })}
        autoComplete="new-password"
        required
        value={props.value.password}
        onChange={(e) => props.onChange({ ...props.value, password: e.currentTarget.value })}
      />
      <PasswordInput
        label={t("account.repeatPassword")}
        autoComplete="new-password"
        required
        value={props.value.repeat}
        onChange={(e) => props.onChange({ ...props.value, repeat: e.currentTarget.value })}
        error={issue === "repeat" && props.value.repeat ? t("account.passwordsDiffer") : undefined}
      />
    </>
  );
}

/** A one-time link, shown once: copy it and send it (e.g. in a message). */
export function LinkBox({ link, name }: { link: NewLink; name: string }) {
  const { t } = useTranslation();
  const url = linkUrl(link.token);
  return (
    <Alert color="teal" icon={<IconLink size={18} />} title={t(`users.link.${link.purpose}Title`, { name })}>
      <Stack gap="xs">
        <Group gap="xs" wrap="nowrap">
          <TextInput value={url} readOnly style={{ flex: 1 }} onFocus={(e) => e.currentTarget.select()} aria-label={t("users.link.url")} />
          <CopyButton value={url}>
            {({ copied, copy }) => (
              <Tooltip label={copied ? t("users.link.copied") : t("users.link.copy")}>
                <ActionIcon size="lg" variant={copied ? "filled" : "light"} color={copied ? "teal" : undefined} onClick={copy} aria-label={t("users.link.copy")}>
                  {copied ? <IconCheck size={18} /> : <IconCopy size={18} />}
                </ActionIcon>
              </Tooltip>
            )}
          </CopyButton>
        </Group>
        <Text size="xs">{t("users.link.hint", { until: fmtDateTime(link.expires_at) })}</Text>
      </Stack>
    </Alert>
  );
}

const SECTIONS = [
  { path: "/settings/users", labelKey: "settings.section.users", admin: true },
  { path: "/settings/roles", labelKey: "settings.section.roles", admin: true },
  { path: "/settings/ai", labelKey: "settings.section.ai", admin: true },
  { path: "/settings/account", labelKey: "settings.section.account", admin: false },
] as const;

/** Settings' sections, for the page header (only "My account" for non-admins). */
export function SettingsNav() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const path = useLocation().pathname;
  const admin = usePermissions().canManage("admin");
  const shown = SECTIONS.filter((s) => admin || !s.admin);
  if (shown.length < 2) return null;
  return (
    <ChoiceTabs
      label={t("nav.settings")}
      value={shown.find((s) => path.startsWith(s.path))?.path ?? shown[0].path}
      onChange={(v) => navigate(v)}
      data={shown.map((s) => ({ value: s.path, label: t(s.labelKey) }))}
    />
  );
}

/** The built-in roles in the reader's language; others as named. */
export function roleLabel(name: string, t: (k: string) => string): string {
  const key = `roles.builtin.${name}`;
  const text = t(key);
  return text === key ? name : text;
}

/** Where "Settings" opens: accounts for an admin, else one's own account. */
export function useSettingsHome(): string | null {
  const perms = usePermissions();
  if (perms.isLoading) return null;
  return perms.canManage("admin") ? "/settings/users" : "/settings/account";
}
