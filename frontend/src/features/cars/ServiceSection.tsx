/**
 * The "Serwis" tab: service & repairs, oil changes and oil top-ups in one
 * list, newest first. They stay separate record types underneath (oil
 * changes drive the oil reminders and the "oil change in" tile), so each row
 * opens its own form; this view only merges them for reading.
 */
import { useMemo, useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Menu,
  Popover,
  ScrollArea,
  Stack,
  Table,
  Text,
  Tooltip,
} from "@mantine/core";
import { IconChevronDown, IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { ChoiceTabs } from "@/components/ChoiceTabs";

import { fmtDate, fmtMoney, fmtNumber } from "@/lib/format";

import { carsApi, type CarRecord, type RecordKind } from "./api";
import { RecordModal } from "./RecordSection";

const KINDS = ["maintenance", "oil-changes", "oil-topups"] as const;
type ServiceKind = (typeof KINDS)[number];
type Filter = "all" | "service" | "oil";

type Row = { kind: ServiceKind; record: CarRecord };

export function ServiceSection({ carId }: { carId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");
  const [editing, setEditing] = useState<{ kind: ServiceKind; record: CarRecord | null } | null>(
    null,
  );

  const results = useQueries({
    queries: KINDS.map((kind) => ({
      queryKey: ["cars", carId, kind],
      queryFn: () => carsApi.records(carId, kind),
    })),
  });
  const loaded = results.every((r) => r.isSuccess);

  const rows = useMemo(() => {
    const all: Row[] = results.flatMap((r, i) =>
      (r.data ?? []).map((record) => ({ kind: KINDS[i], record })),
    );
    const shown = all.filter(
      (row) =>
        filter === "all" || (filter === "service" ? row.kind === "maintenance" : row.kind !== "maintenance"),
    );
    // Newest first; same day → higher odometer first.
    return shown.sort(
      (a, b) =>
        String(b.record.date).localeCompare(String(a.record.date)) ||
        Number(b.record.odometer_km ?? 0) - Number(a.record.odometer_km ?? 0),
    );
  }, [results, filter]);

  const remove = useMutation({
    mutationFn: (row: Row) => carsApi.deleteRecord(carId, row.kind, row.record.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cars", carId] }),
  });

  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <ChoiceTabs
          size="xs"
          label={t("common.show")}
          value={filter}
          onChange={setFilter}
          data={[
            { value: "all", label: t("cars.svc.filter.all") },
            { value: "service", label: t("cars.svc.filter.service") },
            { value: "oil", label: t("cars.svc.filter.oil") },
          ]}
        />
        <Menu position="bottom-end">
          <Menu.Target>
            <Button
              size="xs"
              leftSection={<IconPlus size={14} />}
              rightSection={<IconChevronDown size={14} />}
            >
              {t("cars.addRecord")}
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            {KINDS.map((kind) => (
              <Menu.Item key={kind} onClick={() => setEditing({ kind, record: null })}>
                {t(`cars.svc.kind.${kind}`)}
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
      </Group>

      <ScrollArea>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              {/* Phones: date, type and odometer under what was done. */}
              <Table.Th visibleFrom="sm">{t("cars.f.date")}</Table.Th>
              <Table.Th visibleFrom="sm">{t("cars.f.kind")}</Table.Th>
              <Table.Th>{t("cars.f.title")}</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">{t("cars.f.odometer")}</Table.Th>
              <Table.Th ta="right">{t("cars.f.cost")}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((row) => {
              const r = row.record;
              return (
                <Table.Tr key={`${row.kind}-${r.id}`}>
                  <Table.Td visibleFrom="sm">{fmtDate(r.date as string)}</Table.Td>
                  <Table.Td visibleFrom="sm">
                    <TypeBadge row={row} />
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{describe(row, t)}</Text>
                    <Text size="xs" c="dimmed" hiddenFrom="sm">
                      {[
                        fmtDate(r.date as string),
                        typeLabel(row, t),
                        r.odometer_km != null ? `${fmtNumber(r.odometer_km as number)} km` : "",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </Text>
                  </Table.Td>
                  <Table.Td ta="right" visibleFrom="sm">
                    {r.odometer_km != null ? `${fmtNumber(r.odometer_km as number)} km` : "—"}
                  </Table.Td>
                  <Table.Td ta="right">
                    {r.cost != null ? fmtMoney(r.cost as string, r.currency as string) : "—"}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <Tooltip label={t("finance.action.edit")}>
                        <ActionIcon
                          variant="subtle"
                          onClick={() => setEditing({ kind: row.kind, record: r })}
                        >
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
                          <Stack gap="xs">
                            <Text size="sm">{t("cars.deleteConfirm")}</Text>
                            <Button size="xs" color="red" onClick={() => remove.mutate(row)}>
                              {t("finance.action.delete")}
                            </Button>
                          </Stack>
                        </Popover.Dropdown>
                      </Popover>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              );
            })}
            {loaded && !rows.length && (
              <Table.Tr>
                <Table.Td colSpan={6} ta="center" c="dimmed" py="md">
                  {t("cars.noRecords")}
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      <RecordModal
        carId={carId}
        kind={(editing?.kind ?? "maintenance") as RecordKind}
        record={editing?.record ?? null}
        opened={editing !== null}
        onClose={() => setEditing(null)}
      />
    </Stack>
  );
}

function typeLabel(row: Row, t: (key: string) => string): string {
  return row.kind === "maintenance"
    ? t(`cars.maintenanceKind.${row.record.kind as string}`)
    : t(`cars.svc.kind.${row.kind}`);
}

function TypeBadge({ row }: { row: Row }) {
  const { t } = useTranslation();
  const color = row.kind === "maintenance" ? "gray" : row.kind === "oil-changes" ? "teal" : "blue";
  return (
    <Badge variant="light" color={color}>
      {typeLabel(row, t)}
    </Badge>
  );
}

/** The "What" column: title for service, spec + next due for oil, litres for top-ups. */
function describe(row: Row, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const r = row.record;
  if (row.kind === "maintenance") return String(r.title ?? "");
  if (row.kind === "oil-topups") return `+${fmtNumber(r.litres as string, 2)} l`;
  const next = [
    r.next_due_km ? t("cars.svc.atKm", { km: fmtNumber(r.next_due_km as number) }) : "",
    r.next_due_date ? t("cars.svc.byDate", { date: fmtDate(r.next_due_date as string) }) : "",
  ]
    .filter(Boolean)
    .join(" / ");
  return [
    r.oil_spec ? String(r.oil_spec) : "",
    r.with_filter ? t("cars.svc.withFilter") : "",
    next ? t("cars.svc.next", { due: next }) : "",
  ]
    .filter(Boolean)
    .join(" · ");
}
