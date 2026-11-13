/**
 * The frame around every page. Desktop: a light sidebar (logo, menu
 * sections with icons, you + dark-mode switch at the bottom) next to the
 * page on a light grey background. Phone: a slim top bar and a bottom tab
 * bar with the main sections; "Więcej" opens the full menu.
 */
import {
  ActionIcon,
  AppShell,
  Avatar,
  Box,
  Group,
  Menu,
  NavLink,
  ScrollArea,
  Stack,
  Text,
  ThemeIcon,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure, useMediaQuery } from "@mantine/hooks";
import { IconDots, IconHomeHeart, IconLogout, IconMoon, IconSettings, IconSun } from "@tabler/icons-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";

import { AssistantButton } from "@/features/assistant/AssistantButton";
import { usePermissions } from "@/features/auth/usePermissions";
import { useMe } from "@/features/auth/useMe";

import { activeItem, BOTTOM_BAR, NAV } from "./nav";

const PAGE_BG = "light-dark(var(--mantine-color-gray-0), var(--mantine-color-dark-8))";

export function AppShellLayout({ children }: { children: React.ReactNode }) {
  const [opened, { toggle, close }] = useDisclosure();
  const mobile = useMediaQuery("(max-width: 48em)", false, { getInitialValueInEffect: false });
  const loc = useLocation();
  useEffect(close, [loc.pathname, close]); // a picked page closes the phone menu

  return (
    <AppShell
      header={{ height: 56, collapsed: !mobile }}
      navbar={{ width: 264, breakpoint: "sm", collapsed: { mobile: !opened } }}
      // + the iPhone home-indicator strip when installed as an app
      footer={{ height: "calc(64px + env(safe-area-inset-bottom))", collapsed: !mobile }}
      padding={{ base: "md", sm: "xl" }}
      styles={{ main: { background: PAGE_BG } }}
    >
      <AppShell.Header px="md">
        <Group h="100%" justify="space-between" wrap="nowrap">
          <Brand />
          <ColorSchemeToggle />
        </Group>
      </AppShell.Header>
      <AppShell.Navbar>
        <Box p="md" pb="xs" visibleFrom="sm">
          <Brand />
        </Box>
        <AppShell.Section grow component={ScrollArea} px="sm" py="xs">
          <Menu_ />
        </AppShell.Section>
        <AppShell.Section p="sm" style={{ borderTop: "1px solid var(--mantine-color-default-border)" }}>
          <UserBlock />
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main>
        <Box maw={1400} mx="auto">
          {children}
        </Box>
      </AppShell.Main>
      <AppShell.Footer>
        <BottomBar menuOpened={opened} onMore={toggle} />
      </AppShell.Footer>
      <AssistantButton />
    </AppShell>
  );
}

function Brand() {
  const { t } = useTranslation();
  return (
    <UnstyledButton component={Link} to="/">
      <Group gap="sm" wrap="nowrap">
        <ThemeIcon size={34} radius="md" variant="gradient" gradient={{ from: "indigo.5", to: "violet.5", deg: 135 }}>
          <IconHomeHeart size={20} stroke={1.8} />
        </ThemeIcon>
        <Text fw={700} size="md">
          {t("app.title")}
        </Text>
      </Group>
    </UnstyledButton>
  );
}

function Menu_() {
  const { t } = useTranslation();
  const perms = usePermissions();
  const active = activeItem(useLocation().pathname);
  return (
    <Stack gap={2}>
      {NAV.map((section, i) => {
        const items = section.items.filter((n) => n.module === null || perms.canView(n.module));
        if (!items.length) return null;
        return (
          <Stack key={section.labelKey ?? i} gap={2}>
            {section.labelKey && (
              <Text size="xs" fw={600} c="dimmed" tt="uppercase" px="sm" pt="md" pb={4} style={{ letterSpacing: "0.04em" }}>
                {t(section.labelKey)}
              </Text>
            )}
            {items.map((item) => (
              <NavLink
                key={item.to}
                component={Link}
                to={item.to}
                label={t(item.labelKey)}
                leftSection={<item.icon size={19} stroke={1.7} />}
                active={item === active}
                variant="light"
                styles={{ root: { borderRadius: "var(--mantine-radius-md)" }, label: { fontWeight: 500 } }}
              />
            ))}
          </Stack>
        );
      })}
    </Stack>
  );
}

function ColorSchemeToggle() {
  const { t } = useTranslation();
  const { setColorScheme } = useMantineColorScheme();
  const dark = useComputedColorScheme("light") === "dark";
  const label = t(dark ? "shell.lightMode" : "shell.darkMode");
  return (
    <Tooltip label={label}>
      <ActionIcon variant="subtle" color="gray" size="lg" onClick={() => setColorScheme(dark ? "light" : "dark")} aria-label={label}>
        {dark ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}

async function logout() {
  const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
  // allauth answers 401 once the session is gone — that's the success case.
  await fetch("/api/_allauth/browser/v1/auth/session", {
    method: "DELETE",
    credentials: "include",
    headers: { "X-CSRFToken": csrf },
  }).catch(() => undefined);
  window.location.assign("/auth/login");
}

function UserBlock() {
  const { t } = useTranslation();
  const me = useMe().data;
  const name = [me?.first_name, me?.last_name].filter(Boolean).join(" ") || me?.email || "";
  return (
    <Group gap="xs" wrap="nowrap">
      <Menu position="top-start" width={220}>
        <Menu.Target>
          <UnstyledButton style={{ flex: 1, minWidth: 0, borderRadius: "var(--mantine-radius-md)" }} p={6}>
            <Group gap="sm" wrap="nowrap">
              <Avatar radius="xl" color="indigo" variant="light" name={name} />
              <div style={{ minWidth: 0 }}>
                <Text size="sm" fw={600} truncate>
                  {name}
                </Text>
                {me?.email && me.email !== name && (
                  <Text size="xs" c="dimmed" truncate>
                    {me.email}
                  </Text>
                )}
              </div>
            </Group>
          </UnstyledButton>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item component={Link} to="/settings" leftSection={<IconSettings size={16} />}>
            {t("nav.settings")}
          </Menu.Item>
          <Menu.Divider />
          <Menu.Item color="red" leftSection={<IconLogout size={16} />} onClick={logout}>
            {t("shell.logout")}
          </Menu.Item>
          <Menu.Label>{t("shell.version", { version: __APP_VERSION__ })}</Menu.Label>
        </Menu.Dropdown>
      </Menu>
      <ColorSchemeToggle />
    </Group>
  );
}

function BottomBar({ menuOpened, onMore }: { menuOpened: boolean; onMore: () => void }) {
  const { t } = useTranslation();
  const perms = usePermissions();
  const path = useLocation().pathname;
  const items = BOTTOM_BAR.filter((n) => n.module === null || perms.canView(n.module)).slice(0, 4);
  // A section is current for anything under it (/finance/charts → Finanse).
  const current = menuOpened ? undefined : activeItem(path, items);
  const tab = (key: string, label: string, icon: React.ReactNode, active: boolean, props: object) => (
    <UnstyledButton
      key={key}
      {...props}
      style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2, paddingTop: 8 }}
      c={active ? "var(--mantine-primary-color-filled)" : "dimmed"}
    >
      {icon}
      <Text size="10px" fw={active ? 700 : 500} lh={1.2}>
        {label}
      </Text>
    </UnstyledButton>
  );
  return (
    <Group h="100%" gap={0} wrap="nowrap" align="stretch" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
      {items.map((item) =>
        tab(item.to, t(item.labelKey), <item.icon size={22} stroke={1.7} />, item === current, { component: Link, to: item.to }),
      )}
      {tab("more", t("shell.more"), <IconDots size={22} stroke={1.7} />, menuOpened, { onClick: onMore })}
    </Group>
  );
}
