/**
 * Health — first choose whose health to look at. The next page opens that
 * person's history and new entries default to them.
 */
import { Alert, Avatar, Card, Group, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { healthApi } from "./api";

export function HealthChooserPage() {
  const { t } = useTranslation();
  const people = useQuery({ queryKey: ["health", "people"], queryFn: () => healthApi.people() });

  return (
    <Stack gap="lg">
      <Title order={2}>{t("health.choose.title")}</Title>
      {people.isSuccess && !people.data.length && <Alert color="gray">{t("health.noPeople")}</Alert>}
      <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }}>
        {(people.data ?? []).map((p) => (
          <Card
            key={p.id}
            withBorder
            padding="lg"
            component={Link}
            to={`/health/${p.id}`}
            style={{ textDecoration: "none" }}
          >
            <Group>
              <Avatar color="indigo" radius="xl" size="lg">
                {p.display_name.slice(0, 2).toUpperCase()}
              </Avatar>
              <Text fw={600} size="lg">
                {p.display_name}
              </Text>
            </Group>
          </Card>
        ))}
      </SimpleGrid>
    </Stack>
  );
}
