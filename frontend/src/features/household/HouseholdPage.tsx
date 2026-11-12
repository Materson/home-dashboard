/**
 * Dom — the shopping list (first: it's what's used on the phone in the shop)
 * and the stock at home. Anyone with household access reads; edit changes.
 */
import { useState } from "react";
import { Badge, Group, Paper, Stack, Tabs } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";

import { usePermissions } from "@/features/auth/usePermissions";

import { HOUSEHOLD_KEY, householdApi } from "./api";
import { ShoppingList } from "./ShoppingList";
import { StockTab } from "./StockTab";

export function HouseholdPage() {
  const { t } = useTranslation();
  const canEdit = usePermissions().canEdit("household");
  const [tab, setTab] = useState<string | null>("shopping");

  // All items (unfiltered) — names for the shopping list, counts for the badges.
  const items = useQuery({
    queryKey: [...HOUSEHOLD_KEY, "items", {}],
    queryFn: () => householdApi.items({}),
  });
  const shopping = useQuery({ queryKey: [...HOUSEHOLD_KEY, "shopping"], queryFn: householdApi.shopping });
  const toBuy = (shopping.data ?? []).filter((e) => !e.done_at).length;
  const low = (items.data ?? []).filter((i) => i.below_min).length;

  return (
    <Stack gap="lg">
      <PageHeader title={t("household.title")} subtitle={t("page.household.subtitle")} />
      <Paper withBorder p="md">
        <Tabs value={tab} onChange={setTab} keepMounted={false}>
          <Tabs.List>
            <Tabs.Tab
              value="shopping"
              rightSection={toBuy > 0 ? <Badge size="xs" circle>{toBuy}</Badge> : null}
            >
              {t("household.tab.shopping")}
            </Tabs.Tab>
            <Tabs.Tab
              value="stock"
              rightSection={
                low > 0 ? (
                  <Badge size="xs" color="red" circle>
                    {low}
                  </Badge>
                ) : null
              }
            >
              {t("household.tab.stock")}
            </Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="shopping" pt="md">
            <Group justify="center">
              <div style={{ width: "100%", maxWidth: 640 }}>
                <ShoppingList canEdit={canEdit} itemNames={(items.data ?? []).map((i) => i.name)} />
              </div>
            </Group>
          </Tabs.Panel>
          <Tabs.Panel value="stock" pt="md">
            <StockTab canEdit={canEdit} />
          </Tabs.Panel>
        </Tabs>
      </Paper>
    </Stack>
  );
}
