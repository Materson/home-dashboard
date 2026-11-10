/**
 * Table + add/edit/delete for one field-driven record type. The feature
 * supplies the field list and the three API calls; this handles the rest.
 */
import { type ReactNode, useState } from "react";
import {
  ActionIcon,
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
import { type QueryKey, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { display, isNumeric, type Choices, type FieldDef, type Row } from "./fields";
import { RecordFormModal } from "./RecordFormModal";

export type ExtraColumn = { headerKey: string; numeric?: boolean; render: (r: Row) => ReactNode };

export function RecordList(props: {
  fields: FieldDef[];
  queryKey: QueryKey;
  list: () => Promise<Row[]>;
  save: (payload: Record<string, unknown>, id?: string) => Promise<unknown>;
  remove: (id: string) => Promise<unknown>;
  /** Query keys to refresh after a change (the list's own key is always refreshed). */
  invalidate?: QueryKey[];
  choices?: Choices;
  extraColumns?: ExtraColumn[];
  /** Extra buttons before edit/delete in each row. */
  rowActions?: (r: Row) => ReactNode;
  labels: { add: string; edit: string; empty: string; deleteConfirm: string };
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Row | null | "new">(null);

  const rows = useQuery({ queryKey: props.queryKey, queryFn: props.list });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: props.queryKey });
    for (const key of props.invalidate ?? []) qc.invalidateQueries({ queryKey: key });
  };
  const remove = useMutation({ mutationFn: props.remove, onSuccess: refresh });

  const columns = props.fields.filter((f) => f.column);
  const extra = props.extraColumns ?? [];

  return (
    <Stack gap="sm">
      {!props.readOnly && (
        <Group justify="flex-end">
          <Button size="xs" leftSection={<IconPlus size={14} />} onClick={() => setEditing("new")}>
            {t(props.labels.add)}
          </Button>
        </Group>
      )}
      <ScrollArea>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              {columns.map((f) => (
                <Table.Th key={f.name} ta={isNumeric(f) ? "right" : undefined}>
                  {t(f.labelKey)}
                </Table.Th>
              ))}
              {extra.map((c) => (
                <Table.Th key={c.headerKey} ta={c.numeric ? "right" : undefined}>
                  {t(c.headerKey)}
                </Table.Th>
              ))}
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(rows.data ?? []).map((r) => (
              <Table.Tr key={r.id}>
                {columns.map((f) => (
                  <Table.Td key={f.name} ta={isNumeric(f) ? "right" : undefined}>
                    {display(f, r, t, props.choices)}
                  </Table.Td>
                ))}
                {extra.map((c) => (
                  <Table.Td key={c.headerKey} ta={c.numeric ? "right" : undefined}>
                    {c.render(r)}
                  </Table.Td>
                ))}
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    {props.rowActions?.(r)}
                    {!props.readOnly && (
                      <>
                        <Tooltip label={t("finance.action.edit")}>
                          <ActionIcon variant="subtle" onClick={() => setEditing(r)}>
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
                            <Stack gap="xs" maw={260}>
                              <Text size="sm">{t(props.labels.deleteConfirm)}</Text>
                              <Button size="xs" color="red" onClick={() => remove.mutate(r.id)}>
                                {t("finance.action.delete")}
                              </Button>
                            </Stack>
                          </Popover.Dropdown>
                        </Popover>
                      </>
                    )}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
            {rows.isSuccess && !rows.data.length && (
              <Table.Tr>
                <Table.Td colSpan={columns.length + extra.length + 1} ta="center" c="dimmed" py="md">
                  {t(props.labels.empty)}
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </ScrollArea>

      <RecordFormModal
        fields={props.fields}
        record={editing === "new" ? null : editing}
        opened={editing !== null}
        onClose={() => setEditing(null)}
        onSave={(payload) => props.save(payload, editing && editing !== "new" ? editing.id : undefined)}
        onSaved={refresh}
        titleKey={{ add: props.labels.add, edit: props.labels.edit }}
        choices={props.choices}
      />
    </Stack>
  );
}
