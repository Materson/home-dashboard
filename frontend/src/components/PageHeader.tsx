/**
 * The top of every page: its menu icon, title, a short subtitle and the
 * page's actions on the right (wrapping under the title on a phone).
 */
import type { ReactNode } from "react";
import { Group, Text, ThemeIcon, Title } from "@mantine/core";
import { useLocation } from "react-router-dom";

import { activeItem } from "@/app/nav";

export function PageHeader(props: {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Before the icon, e.g. a back button. */
  before?: ReactNode;
  /** Buttons, filters … on the right. */
  actions?: ReactNode;
  /** Defaults to the menu icon of the current page. */
  icon?: ReactNode | false;
}) {
  const nav = activeItem(useLocation().pathname);
  const NavIcon = nav?.icon;
  const icon = props.icon ?? (NavIcon ? <NavIcon size={22} stroke={1.7} /> : null);
  return (
    <Group justify="space-between" align="center" gap="md" wrap="wrap">
      <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
        {props.before}
        {icon && (
          <ThemeIcon size={42} radius="md" variant="light">
            {icon}
          </ThemeIcon>
        )}
        <div style={{ minWidth: 0 }}>
          <Title order={2} lh={1.2}>
            {props.title}
          </Title>
          {props.subtitle && (
            <Text size="sm" c="dimmed" mt={2}>
              {props.subtitle}
            </Text>
          )}
        </div>
      </Group>
      {props.actions && (
        <Group gap="xs" wrap="wrap" className="page-actions">
          {props.actions}
        </Group>
      )}
    </Group>
  );
}
