/**
 * A change the assistant proposed (Confirm / Cancel) or already made for
 * you (Undo). Fields are shown per kind; values are the real ones (never
 * aliases).
 */
import { Badge, Button, Group, Paper, Stack, Table, Text } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { fmtDate, fmtDateTime, fmtMoney, fmtQty } from "@/lib/format";

import { type Action, type ActionStatus, assistantApi } from "./api";

type Fmt = "money" | "date" | "datetime" | "bool" | "km" | "litres" | "kind" | "repeat" | "list" | "text";
const FIELDS: Record<string, [string, Fmt][]> = {
  "finance.transaction": [
    ["kind", "kind"],
    ["amount", "money"],
    ["date", "date"],
    ["name", "text"],
    ["category", "text"],
    ["person", "text"],
    ["notes", "text"],
  ],
  "cars.fuel": [
    ["car", "text"],
    ["date", "date"],
    ["litres", "litres"],
    ["total_cost", "money"],
    ["price_per_litre", "text"],
    ["odometer_km", "km"],
    ["full_tank", "bool"],
    ["station", "text"],
  ],
  "cars.odometer": [
    ["car", "text"],
    ["date", "date"],
    ["odometer_km", "km"],
  ],
  "notes.note": [
    ["title", "text"],
    ["body", "text"],
    ["checklist", "list"],
    ["remind_at", "datetime"],
    ["repeat", "repeat"],
  ],
};

const STATUS_COLOR: Record<ActionStatus, string> = {
  proposed: "blue",
  done: "teal",
  cancelled: "gray",
  undone: "gray",
  failed: "red",
};

export function ActionCard({ action, onChanged }: { action: Action; onChanged: () => void }) {
  const { t } = useTranslation();
  const decide = useMutation({
    mutationFn: (d: "confirm" | "cancel" | "undo") => assistantApi.decide(action.id, d),
    onSuccess: onChanged,
  });
  const p = action.payload;

  const value = (key: string, fmt: Fmt): string | null => {
    const v = p[key];
    if (v === null || v === undefined || v === "" || (Array.isArray(v) && !v.length)) return null;
    switch (fmt) {
      case "money":
        return fmtMoney(String(v), String(p.currency ?? "PLN"));
      case "date":
        return fmtDate(String(v));
      case "datetime":
        return fmtDateTime(String(v));
      case "bool":
        return v ? t("assistant.yes") : t("assistant.no");
      case "km":
        return `${fmtQty(String(v))} km`;
      case "litres":
        return `${fmtQty(String(v))} l`;
      case "kind":
        return t(`assistant.kind.${String(v)}`);
      case "repeat":
        return t(`notes.repeat.${String(v) || "none"}`);
      case "list":
        return (v as string[]).join(", ");
      default:
        return String(v);
    }
  };

  const rows =
    action.kind === "household.shopping"
      ? ((p.items as { name: string; quantity: string }[]) ?? []).map((i) => [i.name, i.quantity || "—"])
      : (FIELDS[action.kind] ?? [])
          .map(([key, fmt]) => [t(`assistant.f.${key}`), value(key, fmt)])
          .filter(([, v]) => v !== null);

  return (
    <Paper withBorder p="sm" radius="md" bg="var(--mantine-color-body)">
      <Stack gap="xs">
        <Group justify="space-between">
          <Text size="sm" fw={600}>
            {t(`assistant.action.${action.kind}`)}
          </Text>
          <Badge size="sm" color={STATUS_COLOR[action.status]} variant="light">
            {t(`assistant.status.${action.status}${action.auto && action.status === "done" ? "Auto" : ""}`)}
          </Badge>
        </Group>
        <Table withRowBorders={false} verticalSpacing={2} fz="sm">
          <Table.Tbody>
            {rows.map(([label, v], i) => (
              <Table.Tr key={i}>
                <Table.Td c="dimmed" w="40%">
                  {label}
                </Table.Td>
                <Table.Td>{v}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {action.error && (
          <Text size="xs" c="red">
            {action.error}
          </Text>
        )}
        {decide.isError && (
          <Text size="xs" c="red">
            {(decide.error as Error).message}
          </Text>
        )}
        {action.status === "proposed" && (
          <Group gap="xs">
            <Button size="xs" color="teal" loading={decide.isPending && decide.variables === "confirm"} onClick={() => decide.mutate("confirm")}>
              {t("assistant.confirm")}
            </Button>
            <Button size="xs" variant="subtle" color="gray" loading={decide.isPending && decide.variables === "cancel"} onClick={() => decide.mutate("cancel")}>
              {t("notes.cancel")}
            </Button>
          </Group>
        )}
        {action.status === "done" && (
          <Group gap="xs">
            <Button size="xs" variant="subtle" color="gray" loading={decide.isPending} onClick={() => decide.mutate("undo")}>
              {t("assistant.undo")}
            </Button>
          </Group>
        )}
      </Stack>
    </Paper>
  );
}
