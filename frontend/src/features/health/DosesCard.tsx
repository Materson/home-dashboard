/**
 * One day's medicine doses for a person, with Taken / Skipped buttons.
 * Marking a dose only needs read access to that person's health, so a child
 * can confirm their own doses. Answering early cancels the pending reminder.
 */
import { useState } from "react";
import { ActionIcon, Badge, Button, Group, Paper, Stack, Text, Title } from "@mantine/core";
import { IconChevronLeft, IconChevronRight } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { fmtDate, fmtTime, isoDate } from "@/lib/format";

import { healthApi, type Dose, type DoseStatus } from "./api";

export function DosesCard({ personId }: { personId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [day, setDay] = useState(() => new Date());
  const dayIso = isoDate(day);
  const isToday = dayIso === isoDate(new Date());

  const doses = useQuery({
    queryKey: ["health", "doses", personId, dayIso],
    queryFn: () => healthApi.doses(dayIso, personId),
  });
  const set = useMutation({
    mutationFn: ({ id, status }: { id: string; status: DoseStatus }) => healthApi.setDose(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["health", "doses", personId] }),
  });

  const shift = (n: number) => setDay((d) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n));
  const time = (d: Dose) => fmtTime(d.scheduled_at);

  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="sm">
        <Title order={5}>{t("health.doses.title")}</Title>
        <Group gap={4}>
          <ActionIcon variant="subtle" aria-label={t("health.doses.prevDay")} onClick={() => shift(-1)}>
            <IconChevronLeft size={18} />
          </ActionIcon>
          <Text size="sm" w={110} ta="center">
            {isToday ? t("health.doses.today") : fmtDate(dayIso)}
          </Text>
          <ActionIcon variant="subtle" aria-label={t("health.doses.nextDay")} onClick={() => shift(1)}>
            <IconChevronRight size={18} />
          </ActionIcon>
        </Group>
      </Group>

      {doses.isSuccess && !doses.data.length && (
        <Text size="sm" c="dimmed">
          {t("health.doses.none")}
        </Text>
      )}
      <Stack gap="xs">
        {(doses.data ?? []).map((d) => {
          const overdue = d.status === "pending" && new Date(d.scheduled_at) < new Date();
          return (
            <Group key={d.id} justify="space-between" wrap="nowrap">
              <Group gap="sm" wrap="nowrap">
                <Text fw={600} w={48}>
                  {time(d)}
                </Text>
                <Text size="sm">
                  {d.medication_name}
                  {d.dosage && (
                    <Text span c="dimmed">
                      {" "}
                      · {d.dosage}
                    </Text>
                  )}
                </Text>
                {d.status !== "pending" && (
                  <Badge color={d.status === "taken" ? "teal" : "gray"} variant="light">
                    {t(`health.doses.status.${d.status}`)}
                  </Badge>
                )}
                {overdue && (
                  <Badge color="orange" variant="light">
                    {t("health.doses.overdue")}
                  </Badge>
                )}
              </Group>
              <Group gap="xs" wrap="nowrap">
                {d.status === "pending" ? (
                  <>
                    <Button
                      size="xs"
                      color="teal"
                      onClick={() => set.mutate({ id: d.id, status: "taken" })}
                    >
                      {t("health.doses.take")}
                    </Button>
                    <Button
                      size="xs"
                      variant="default"
                      onClick={() => set.mutate({ id: d.id, status: "skipped" })}
                    >
                      {t("health.doses.skip")}
                    </Button>
                  </>
                ) : (
                  <Button
                    size="xs"
                    variant="subtle"
                    onClick={() => set.mutate({ id: d.id, status: "pending" })}
                  >
                    {t("health.doses.undo")}
                  </Button>
                )}
              </Group>
            </Group>
          );
        })}
      </Stack>
    </Paper>
  );
}
