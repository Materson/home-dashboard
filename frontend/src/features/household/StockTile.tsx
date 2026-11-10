/** Overview tile: how much is on the shopping list, what runs low, and what
 *  to use first. Links to the Home page. */
import { Anchor, Badge, Group, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { fmtDate } from "@/lib/format";

import { HOUSEHOLD_KEY, householdApi } from "./api";

export function StockTile() {
  const { t } = useTranslation();
  const items = useQuery({ queryKey: [...HOUSEHOLD_KEY, "items", {}], queryFn: () => householdApi.items({}) });
  const shopping = useQuery({ queryKey: [...HOUSEHOLD_KEY, "shopping"], queryFn: householdApi.shopping });
  const expiring = useQuery({ queryKey: [...HOUSEHOLD_KEY, "expiring"], queryFn: () => householdApi.expiring(3) });

  const toBuy = (shopping.data ?? []).filter((e) => !e.done_at).length;
  const low = (items.data ?? []).filter((i) => i.below_min);
  const first = (expiring.data ?? []).slice(0, 5);

  return (
    <Stack gap="xs">
      <Group gap="xs">
        <Anchor component={Link} to="/household" size="sm">
          {t("household.tile.toBuy", { count: toBuy })}
        </Anchor>
        {low.length > 0 && (
          <Badge color="red" variant="light">
            {t("household.tile.low", { count: low.length })}
          </Badge>
        )}
      </Group>
      {first.length > 0 ? (
        first.map((b) => (
          <Group key={b.id} gap="xs" wrap="nowrap">
            <Badge size="sm" color={b.status === "expired" ? "red" : "orange"} variant="light">
              {b.status === "expired" ? t("household.expired") : fmtDate(b.expiry_date)}
            </Badge>
            <Text size="sm">{b.item_name}</Text>
          </Group>
        ))
      ) : (
        <Text size="sm" c="dimmed">
          {t("household.tile.nothingExpiring")}
        </Text>
      )}
    </Stack>
  );
}
