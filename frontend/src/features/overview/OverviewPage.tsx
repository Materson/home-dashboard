import { Grid, Paper, Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";

/**
 * The home overview. Later milestones will fill the tiles with real data
 * from upcoming reminders, this week's calendar, low stock, and month spend.
 */
export function OverviewPage() {
  const { t } = useTranslation();
  return (
    <Stack gap="lg">
      <Title order={2}>{t("nav.overview")}</Title>
      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper withBorder p="md">
            <Text fw={600}>{t("overview.upcomingReminders")}</Text>
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper withBorder p="md">
            <Text fw={600}>{t("overview.calendar")}</Text>
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper withBorder p="md">
            <Text fw={600}>{t("overview.stock")}</Text>
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
