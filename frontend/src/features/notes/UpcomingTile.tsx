/** Overview tile: my next reminders (notes, visits, doses, expiries …).
 *  Private ones show only a generic title — the server already redacts them. */
import { Anchor, Group, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconBell } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { fmtDateTime } from "@/lib/format";

type Upcoming = { id: string; title: string; due_at: string | null; link: string };

async function upcoming(): Promise<Upcoming[]> {
  const resp = await fetch("/api/reminders/upcoming", { credentials: "include" });
  if (!resp.ok) throw new Error("upcoming failed");
  return (await resp.json()) as Upcoming[];
}

export function UpcomingTile() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["reminders", "upcoming"], queryFn: upcoming, staleTime: 60_000 });
  const rows = (q.data ?? []).slice(0, 6);
  if (q.isSuccess && !rows.length) {
    return (
      <Text size="sm" c="dimmed">
        {t("overview.noReminders")}
      </Text>
    );
  }
  return (
    <Stack gap={0}>
      {rows.map((r, i) => (
        <Group
          key={r.id}
          gap="sm"
          wrap="nowrap"
          py={8}
          style={i ? { borderTop: "1px solid var(--mantine-color-default-border)" } : undefined}
        >
          <ThemeIcon variant="light" size={32} radius="md">
            <IconBell size={16} />
          </ThemeIcon>
          <div style={{ minWidth: 0, flex: 1 }}>
            {r.link ? (
              <Anchor component={Link} to={r.link} size="sm" fw={500} c="var(--mantine-color-text)" lineClamp={1}>
                {r.title}
              </Anchor>
            ) : (
              <Text size="sm" fw={500} lineClamp={1}>
                {r.title}
              </Text>
            )}
            <Text size="xs" c="dimmed">
              {fmtDateTime(r.due_at)}
            </Text>
          </div>
        </Group>
      ))}
    </Stack>
  );
}
