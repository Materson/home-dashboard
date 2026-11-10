/**
 * Zapasy — what's at home. "Use first" lists what's expired or about to;
 * the table shows each item's stock (red when below its minimum) and the
 * nearest expiry; − uses one (from what expires first), + adds a purchase.
 * Clicking an item opens its batches.
 */
import { useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Drawer,
  Group,
  Paper,
  Popover,
  SegmentedControl,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconArchive, IconCheck, IconMinus, IconPencil, IconPlus, IconSearch, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { Row } from "@/components/records/fields";
import { RecordFormModal } from "@/components/records/RecordFormModal";
import { fmtDate, fmtQty, isoDate } from "@/lib/format";

import { type Batch, type BatchStatus, HOUSEHOLD_KEY, householdApi, type Item } from "./api";
import { BATCH_FIELDS, ITEM_FIELDS, UNIT_SUGGESTIONS } from "./fields";

const STATUS_COLOR: Record<BatchStatus, string> = {
  expired: "red",
  soon: "orange",
  ok: "teal",
  unknown: "gray",
  finished: "gray",
};
const SOON_DAYS = 3; // same as the server's EXPIRY_SOON_DAYS

/** Status of an expiry date, as the server computes it for batches. */
export function expiryStatus(expiry: string | null, today = new Date()): BatchStatus {
  if (!expiry) return "unknown";
  const t = isoDate(today);
  if (expiry < t) return "expired";
  const soon = new Date(today);
  soon.setDate(soon.getDate() + SOON_DAYS);
  return expiry <= isoDate(soon) ? "soon" : "ok";
}

const qty = fmtQty;

type CategoryFilter = "all" | "food" | "cleaning";
type BatchForm = { itemId: string; batch: Batch | null };

export function StockTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search, 250);
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [itemForm, setItemForm] = useState<Item | null | "new">(null);
  const [batchForm, setBatchForm] = useState<BatchForm | null>(null);

  const filters = { q, category: category === "all" ? "" : category };
  const items = useQuery({
    queryKey: [...HOUSEHOLD_KEY, "items", filters],
    queryFn: () => householdApi.items(filters),
  });
  const expiring = useQuery({ queryKey: [...HOUSEHOLD_KEY, "expiring"], queryFn: () => householdApi.expiring(SOON_DAYS) });
  const refresh = () => qc.invalidateQueries({ queryKey: HOUSEHOLD_KEY });

  const consume = useMutation({ mutationFn: (id: string) => householdApi.consume(id), onSuccess: refresh });
  const archive = useMutation({ mutationFn: householdApi.archiveItem, onSuccess: refresh });
  const finish = useMutation({ mutationFn: householdApi.finishBatch, onSuccess: refresh });

  const opened = items.data?.find((i) => i.id === openId) ?? null;
  const suggestions = { unit: UNIT_SUGGESTIONS };

  return (
    <Stack gap="md">
      {(expiring.data?.length ?? 0) > 0 && (
        <Paper withBorder p="md" bg="var(--mantine-color-orange-light)">
          <Title order={6} mb="xs">
            {t("household.useFirst")}
          </Title>
          <Stack gap={6}>
            {expiring.data!.map((b) => (
              <Group key={b.id} justify="space-between" wrap="nowrap">
                <Group gap="xs" wrap="nowrap">
                  <Badge color={STATUS_COLOR[b.status]} variant="filled" size="sm">
                    {b.status === "expired" ? t("household.expired") : fmtDate(b.expiry_date)}
                  </Badge>
                  <Text size="sm" fw={500}>
                    {b.item_name}
                  </Text>
                  <Text size="sm" c="dimmed">
                    {qty(b.quantity)} {b.unit}
                  </Text>
                </Group>
                {canEdit && (
                  <Tooltip label={t("household.finishBatch")}>
                    <ActionIcon variant="subtle" onClick={() => finish.mutate(b.id)}>
                      <IconCheck size={16} />
                    </ActionIcon>
                  </Tooltip>
                )}
              </Group>
            ))}
          </Stack>
        </Paper>
      )}

      <Group justify="space-between">
        <Group>
          <TextInput
            leftSection={<IconSearch size={16} />}
            placeholder={t("household.search")}
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
            w={240}
          />
          <SegmentedControl
            value={category}
            onChange={(v) => setCategory(v as CategoryFilter)}
            data={[
              { value: "all", label: t("household.filter.all") },
              { value: "food", label: t("household.category.food") },
              { value: "cleaning", label: t("household.category.cleaning") },
            ]}
          />
        </Group>
        {canEdit && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setItemForm("new")}>
            {t("household.addItem")}
          </Button>
        )}
      </Group>

      <Paper withBorder>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("household.f.name")}</Table.Th>
              <Table.Th ta="right">{t("household.stock")}</Table.Th>
              <Table.Th>{t("household.nextExpiry")}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(items.data ?? []).map((item) => (
              <Table.Tr key={item.id} onClick={() => setOpenId(item.id)} style={{ cursor: "pointer" }}>
                <Table.Td>
                  <Text fw={600}>{item.name}</Text>
                  {item.notes && (
                    <Text size="xs" c="dimmed" lineClamp={1}>
                      {item.notes}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td ta="right">
                  <Group gap={6} justify="flex-end" wrap="nowrap">
                    {item.below_min && (
                      <Tooltip label={t("household.belowMin", { min: qty(item.min_quantity), unit: item.unit })}>
                        <Badge color="red" variant="light" size="sm">
                          {t("household.low")}
                        </Badge>
                      </Tooltip>
                    )}
                    <Text fw={600} c={Number(item.stock) === 0 ? "dimmed" : undefined}>
                      {qty(item.stock)} {item.unit}
                    </Text>
                  </Group>
                </Table.Td>
                <Table.Td>
                  {item.next_expiry ? (
                    <Badge color={STATUS_COLOR[expiryStatus(item.next_expiry)]} variant="light">
                      {fmtDate(item.next_expiry)}
                    </Badge>
                  ) : (
                    "—"
                  )}
                </Table.Td>
                <Table.Td onClick={(e) => e.stopPropagation()}>
                  {canEdit && (
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <Tooltip label={t("household.useOne")}>
                        <ActionIcon
                          variant="light"
                          disabled={Number(item.stock) <= 0}
                          onClick={() => consume.mutate(item.id)}
                        >
                          <IconMinus size={16} />
                        </ActionIcon>
                      </Tooltip>
                      <Tooltip label={t("household.addBatch")}>
                        <ActionIcon variant="light" onClick={() => setBatchForm({ itemId: item.id, batch: null })}>
                          <IconPlus size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Group>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
            {items.isSuccess && !items.data.length && (
              <Table.Tr>
                <Table.Td colSpan={4} ta="center" c="dimmed" py="md">
                  {search || category !== "all" ? t("household.noMatches") : t("household.empty")}
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      <ItemDrawer
        item={opened}
        canEdit={canEdit}
        onClose={() => setOpenId(null)}
        onEdit={(item) => setItemForm(item)}
        onArchive={(item) => {
          archive.mutate(item.id);
          setOpenId(null);
        }}
        onBatch={(batch) => opened && setBatchForm({ itemId: opened.id, batch })}
        onChanged={refresh}
      />

      <RecordFormModal
        fields={ITEM_FIELDS}
        record={itemForm === "new" ? null : (itemForm as Row | null)}
        opened={itemForm !== null}
        onClose={() => setItemForm(null)}
        onSave={(payload) => householdApi.saveItem(payload, itemForm && itemForm !== "new" ? itemForm.id : undefined)}
        onSaved={refresh}
        titleKey={{ add: "household.addItem", edit: "household.editItem" }}
        suggestions={suggestions}
        defaults={category === "all" ? undefined : { category }}
      />
      <RecordFormModal
        fields={BATCH_FIELDS}
        record={(batchForm?.batch as Row | null) ?? null}
        opened={batchForm !== null}
        onClose={() => setBatchForm(null)}
        onSave={(payload) =>
          householdApi.saveBatch(payload, { itemId: batchForm?.itemId, batchId: batchForm?.batch?.id })
        }
        onSaved={refresh}
        titleKey={{ add: "household.addBatch", edit: "household.editBatch" }}
      />
    </Stack>
  );
}

function ItemDrawer(props: {
  item: Item | null;
  canEdit: boolean;
  onClose: () => void;
  onEdit: (item: Item) => void;
  onArchive: (item: Item) => void;
  onBatch: (batch: Batch | null) => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [showFinished, setShowFinished] = useState(false);
  const item = props.item;
  const batches = useQuery({
    queryKey: [...HOUSEHOLD_KEY, "batches", item?.id, showFinished],
    queryFn: () => householdApi.batches(item!.id, showFinished),
    enabled: !!item,
  });
  const finish = useMutation({ mutationFn: householdApi.finishBatch, onSuccess: props.onChanged });
  const remove = useMutation({ mutationFn: householdApi.deleteBatch, onSuccess: props.onChanged });

  return (
    <Drawer opened={!!item} onClose={props.onClose} position="right" size="md" title={item?.name ?? ""}>
      {item && (
        <Stack>
          <Group gap="xs">
            <Badge variant="light">{t(`household.category.${item.category}`)}</Badge>
            {item.min_quantity != null && (
              <Text size="sm" c="dimmed">
                {t("household.minIs", { min: qty(item.min_quantity), unit: item.unit })}
              </Text>
            )}
          </Group>
          {item.notes && (
            <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
              {item.notes}
            </Text>
          )}
          {props.canEdit && (
            <Group gap="xs">
              <Button size="xs" leftSection={<IconPlus size={14} />} onClick={() => props.onBatch(null)}>
                {t("household.addBatch")}
              </Button>
              <Button size="xs" variant="light" leftSection={<IconPencil size={14} />} onClick={() => props.onEdit(item)}>
                {t("finance.action.edit")}
              </Button>
              <Popover withArrow>
                <Popover.Target>
                  <Button size="xs" variant="subtle" color="gray" leftSection={<IconArchive size={14} />}>
                    {t("household.archiveItem")}
                  </Button>
                </Popover.Target>
                <Popover.Dropdown>
                  <Stack gap="xs" maw={240}>
                    <Text size="sm">{t("household.archiveConfirm")}</Text>
                    <Button size="xs" color="red" onClick={() => props.onArchive(item)}>
                      {t("household.archiveItem")}
                    </Button>
                  </Stack>
                </Popover.Dropdown>
              </Popover>
            </Group>
          )}

          <Group justify="space-between">
            <Title order={6}>{t("household.batches")}</Title>
            <Switch
              size="xs"
              label={t("household.showFinished")}
              checked={showFinished}
              onChange={(e) => setShowFinished(e.currentTarget.checked)}
            />
          </Group>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t("household.f.quantity")}</Table.Th>
                <Table.Th>{t("household.f.expiry")}</Table.Th>
                <Table.Th>{t("household.f.addedOn")}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(batches.data ?? []).map((b) => (
                <Table.Tr key={b.id} c={b.finished_on ? "dimmed" : undefined}>
                  <Table.Td>
                    {qty(b.quantity)} {item.unit}
                  </Table.Td>
                  <Table.Td>
                    {b.finished_on ? (
                      <Text size="sm" c="dimmed">
                        {t("household.finishedOn", { date: fmtDate(b.finished_on) })}
                      </Text>
                    ) : b.expiry_date ? (
                      <Badge color={STATUS_COLOR[b.status]} variant="light">
                        {fmtDate(b.expiry_date)}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </Table.Td>
                  <Table.Td>{fmtDate(b.added_on)}</Table.Td>
                  <Table.Td>
                    {props.canEdit && (
                      <Group gap={2} justify="flex-end" wrap="nowrap">
                        {!b.finished_on && (
                          <Tooltip label={t("household.finishBatch")}>
                            <ActionIcon variant="subtle" onClick={() => finish.mutate(b.id)}>
                              <IconCheck size={16} />
                            </ActionIcon>
                          </Tooltip>
                        )}
                        <ActionIcon variant="subtle" onClick={() => props.onBatch(b)} aria-label={t("finance.action.edit")}>
                          <IconPencil size={16} />
                        </ActionIcon>
                        <ActionIcon variant="subtle" color="red" onClick={() => remove.mutate(b.id)} aria-label={t("finance.action.delete")}>
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Group>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
              {batches.isSuccess && !batches.data.length && (
                <Table.Tr>
                  <Table.Td colSpan={4} ta="center" c="dimmed" py="sm">
                    {t("household.noStock")}
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Stack>
      )}
    </Drawer>
  );
}
