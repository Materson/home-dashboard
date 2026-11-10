import { AppShell, Burger, Group, NavLink, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { usePermissions, type ModuleKey } from "@/features/auth/usePermissions";

type NavItem = { to: string; labelKey: string; module: ModuleKey | null };

type NavGroup = NavItem & { children?: NavItem[] };

const NAV: NavGroup[] = [
  { to: "/", labelKey: "nav.overview", module: null },
  {
    to: "/finance",
    labelKey: "nav.finance",
    module: "finance",
    children: [
      { to: "/finance", labelKey: "nav.transactions", module: "finance" },
      { to: "/finance/loans", labelKey: "nav.loans", module: "finance" },
      { to: "/finance/debts", labelKey: "nav.debts", module: "finance" },
    ],
  },
  { to: "/cars", labelKey: "nav.cars", module: "cars" },
  {
    to: "/health",
    labelKey: "nav.health",
    module: "health",
    children: [
      { to: "/health", labelKey: "nav.healthRecords", module: "health" },
      { to: "/health/cabinet", labelKey: "nav.cabinet", module: "health" },
    ],
  },
  { to: "/household", labelKey: "nav.household", module: "household" },
  { to: "/calendar", labelKey: "nav.calendar", module: "calendar" },
  { to: "/notes", labelKey: "nav.notes", module: "notes" },
  { to: "/assistant", labelKey: "nav.assistant", module: "assistant" },
  { to: "/people", labelKey: "nav.people", module: "people" },
  { to: "/settings", labelKey: "nav.settings", module: null },
];

export function AppShellLayout({ children }: { children: React.ReactNode }) {
  const [opened, { toggle }] = useDisclosure();
  const perms = usePermissions();
  const { t } = useTranslation();
  const loc = useLocation();

  const visible = NAV.filter((n) => n.module === null || perms.canView(n.module));

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700}>{t("app.title")}</Text>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        {visible.map((item) => {
          const active =
            loc.pathname === item.to || (item.to !== "/" && loc.pathname.startsWith(item.to));
          // "/health/<person>" belongs to "/health" (Historia zdrowia), "/health/cabinet"
          // to Apteczka: the longest child path the URL sits under wins.
          const activeChild = item.children
            ?.filter((c) => loc.pathname === c.to || loc.pathname.startsWith(`${c.to}/`))
            .sort((a, b) => b.to.length - a.to.length)[0]?.to;
          return (
            <NavLink
              key={item.to}
              component={Link}
              to={item.to}
              label={t(item.labelKey)}
              active={active}
              defaultOpened={active && !!item.children?.length}
            >
              {item.children?.map((child) => (
                <NavLink
                  key={child.to}
                  component={Link}
                  to={child.to}
                  label={t(child.labelKey)}
                  active={child.to === activeChild}
                />
              ))}
            </NavLink>
          );
        })}
      </AppShell.Navbar>
      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  );
}
