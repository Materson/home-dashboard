import { Grid, Paper, Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";

import { usePermissions } from "@/features/auth/usePermissions";
import { StockTile } from "@/features/household/StockTile";
import { UpcomingTile } from "@/features/notes/UpcomingTile";

/**
 * The home overview: my next reminders and the household's stock; this
 * week's calendar and month spend come with later milestones.
 */
export function OverviewPage() {
  const { t } = useTranslation();
  const canViewHousehold = usePermissions().canView("household");
  return (
    <Stack gap="lg">
      <Title order={2}>{t("nav.overview")}</Title>
      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper withBorder p="md">
            <Text fw={600} mb="xs">
              {t("overview.upcomingReminders")}
            </Text>
            <UpcomingTile />
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper withBorder p="md">
            <Text fw={600}>{t("overview.calendar")}</Text>
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper withBorder p="md">
            <Text fw={600} mb="xs">
              {t("overview.stock")}
            </Text>
            {canViewHousehold && <StockTile />}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper withBorder p="md">
            <Text fw={600}>{t("overview.spend")}</Text>
          </Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
