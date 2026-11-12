/** Overview tile: my next reminders (notes, visits, doses, expiries …).
 *  Private ones show only a generic title — the server already redacts them. */
import { Anchor, Group, Stack, Text } from "@mantine/core";
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
    <Stack gap={4}>
      {rows.map((r) => (
        <Group key={r.id} gap="xs" wrap="nowrap">
          <Text size="sm" c="dimmed" w={110} style={{ flexShrink: 0 }}>
            {fmtDateTime(r.due_at)}
          </Text>
          {r.link ? (
            <Anchor component={Link} to={r.link} size="sm" lineClamp={1}>
              {r.title}
            </Anchor>
          ) : (
            <Text size="sm" lineClamp={1}>
              {r.title}
            </Text>
          )}
        </Group>
      ))}
    </Stack>
  );
}
