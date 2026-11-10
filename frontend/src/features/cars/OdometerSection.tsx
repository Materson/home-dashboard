/**
 * The "Licznik" tab: every odometer value the car has, from all entries
 * (fill-ups, service, oil, …) plus manual readings, newest first. Only manual
 * readings are edited here — other entries are edited in their own tab, so
 * this view never holds a stale copy.
 */
import { useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Popover,
  ScrollArea,
  Stack,
  Table,
  Text,
  Tooltip,
} from "@mantine/core";
import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { fmtDate, fmtNumber } from "@/lib/format";

import { carsApi, type CarRecord } from "./api";
import { RecordModal } from "./RecordSection";

export function OdometerSection({ carId }: { carId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<CarRecord | null | "new">(null);

  const history = useQuery({
    queryKey: ["cars", carId, "odometer-history"],
    queryFn: () => carsApi.odometerHistory(carId),
  });
  // Full manual-reading records, needed to open them in the edit form.
  const manual = useQuery({
    queryKey: ["cars", carId, "odometer"],
    queryFn: () => carsApi.records(carId, "odometer"),
  });
  const remove = useMutation({
    mutationFn: (id: string) => carsApi.deleteRecord(carId, "odometer", id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cars", carId] }),
  });

  const points = history.data ?? [];

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="flex-start">
        <Text size="sm" c="dimmed" maw={560}>
          {t("cars.odo.hint")}
        </Text>
        <Button size="xs" leftSection={<IconPlus size={14} />} onClick={() => setEditing("new")}>
          {t("cars.odo.addReading")}
        </Button>
      </Group>
      <ScrollArea>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("cars.f.date")}</Table.Th>
              <Table.Th ta="right">{t("cars.f.odometer")}</Table.Th>
              <Table.Th ta="right">{t("cars.odo.since")}</Table.Th>
              <Table.Th>{t("cars.odo.source")}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {points.map((p, i) => {
              const older = points[i + 1];
              const delta = older ? p.odometer_km - older.odometer_km : null;
              const record =
                p.source === "odometer" ? manual.data?.find((r) => r.id === p.record_id) : undefined;
              return (
                <Table.Tr key={`${p.source}-${p.record_id ?? "initial"}`}>
                  <Table.Td>{fmtDate(p.date)}</Table.Td>
                  <Table.Td ta="right">{fmtNumber(p.odometer_km)} km</Table.Td>
                  <Table.Td ta="right" c={delta !== null && delta < 0 ? "red" : "dimmed"}>
                    {delta ? `${delta > 0 ? "+" : ""}${fmtNumber(delta)} km` : ""}
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="light" color={p.source === "odometer" ? "indigo" : "gray"}>
                      {t(`cars.odo.src.${p.source}`)}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    {record && (
                      <Group gap={4} justify="flex-end" wrap="nowrap">
                        <Tooltip label={t("finance.action.edit")}>
                          <ActionIcon variant="subtle" onClick={() => setEditing(record)}>
                            <IconPencil size={16} />
                          </ActionIcon>
                        </Tooltip>
                        <Popover withArrow>
                          <Popover.Target>
                            <ActionIcon
                              variant="subtle"
                              color="red"
                              aria-label={t("finance.action.delete")}
                            >
                              <IconTrash size={16} />
                            </ActionIcon>
                          </Popover.Target>
                          <Popover.Dropdown>
                            <Button size="xs" color="red" onClick={() => remove.mutate(record.id)}>
                              {t("finance.action.delete")}
                            </Button>
                          </Popover.Dropdown>
                        </Popover>
                      </Group>
                    )}
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      <RecordModal
        carId={carId}
        kind="odometer"
        record={editing === "new" ? null : editing}
        opened={editing !== null}
        onClose={() => setEditing(null)}
      />
    </Stack>
  );
}
