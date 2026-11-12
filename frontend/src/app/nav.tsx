/**
 * The menu: sections of pages with their icons. The sidebar, the phone's
 * bottom bar and page headers all read it, so a page has one icon everywhere.
 */
import {
  IconBuildingBank,
  IconCar,
  IconCategory,
  IconChartDonut3,
  IconFirstAidKit,
  IconHeartbeat,
  IconHome,
  IconLayoutDashboard,
  IconNotes,
  IconReceipt2,
  IconSettings,
  IconSparkles,
  IconTrendingUp,
  IconUserDollar,
  IconUsers,
  type Icon,
} from "@tabler/icons-react";

import type { ModuleKey } from "@/features/auth/usePermissions";

export type NavItem = { to: string; labelKey: string; module: ModuleKey | null; icon: Icon };
export type NavSection = { labelKey: string | null; items: NavItem[] };

export const NAV: NavSection[] = [
  {
    labelKey: null,
    items: [
      { to: "/", labelKey: "nav.overview", module: null, icon: IconLayoutDashboard },
      { to: "/assistant", labelKey: "nav.assistant", module: "assistant", icon: IconSparkles },
    ],
  },
  {
    labelKey: "nav.finance",
    items: [
      { to: "/finance", labelKey: "nav.transactions", module: "finance", icon: IconReceipt2 },
      { to: "/finance/charts", labelKey: "nav.charts", module: "finance", icon: IconChartDonut3 },
      { to: "/finance/investments", labelKey: "nav.investments", module: "finance", icon: IconTrendingUp },
      { to: "/finance/loans", labelKey: "nav.loans", module: "finance", icon: IconBuildingBank },
      { to: "/finance/debts", labelKey: "nav.debts", module: "finance", icon: IconUserDollar },
      { to: "/finance/categories", labelKey: "nav.categories", module: "finance", icon: IconCategory },
    ],
  },
  {
    labelKey: "nav.section.family",
    items: [
      { to: "/health", labelKey: "nav.health", module: "health", icon: IconHeartbeat },
      { to: "/health/cabinet", labelKey: "nav.cabinet", module: "health", icon: IconFirstAidKit },
      { to: "/cars", labelKey: "nav.cars", module: "cars", icon: IconCar },
      { to: "/household", labelKey: "nav.household", module: "household", icon: IconHome },
      { to: "/notes", labelKey: "nav.notes", module: "notes", icon: IconNotes },
      // Kalendarz comes back with the Google Calendar milestone (no page yet).
    ],
  },
  {
    labelKey: "nav.section.manage",
    items: [
      { to: "/people", labelKey: "nav.people", module: "people", icon: IconUsers },
      { to: "/settings", labelKey: "nav.settings", module: null, icon: IconSettings },
    ],
  },
];

export const ALL_ITEMS = NAV.flatMap((s) => s.items);

/** The menu entry a URL belongs to: the longest path it sits under
 *  ("/health/<person>" → Zdrowie, "/health/cabinet" → Apteczka). */
export function activeItem(pathname: string, items: NavItem[] = ALL_ITEMS): NavItem | undefined {
  return items
    .filter((i) => pathname === i.to || (i.to !== "/" && pathname.startsWith(`${i.to}/`)))
    .sort((a, b) => b.to.length - a.to.length)[0];
}

/** The phone's bottom bar: the first four of these the user may open, then "Więcej". */
export const BOTTOM_BAR: { to: string; labelKey: string; module: ModuleKey | null; icon: Icon }[] = [
  { to: "/", labelKey: "nav.overview", module: null, icon: IconLayoutDashboard },
  { to: "/finance", labelKey: "nav.finance", module: "finance", icon: IconReceipt2 },
  { to: "/health", labelKey: "nav.health", module: "health", icon: IconHeartbeat },
  { to: "/notes", labelKey: "nav.notes", module: "notes", icon: IconNotes },
  { to: "/household", labelKey: "nav.household", module: "household", icon: IconHome },
  { to: "/cars", labelKey: "nav.cars", module: "cars", icon: IconCar },
];
