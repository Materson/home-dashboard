/**
 * Apteczka — the household medicine cabinet: what each medicine is for,
 * who may take it, dosage notes, and every box with its *real* expiry
 * (printed date or N days after opening, whichever comes first).
 *
 * Anyone with health access can read it (children too); changes need
 * health:edit.
 */
import { useMemo, useState } from "react";
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
import { IconCheck, IconLockOpen, IconPencil, IconPlus, IconSearch, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { RecordFormModal } from "@/components/records/RecordFormModal";
import type { Row } from "@/components/records/fields";
import { usePermissions } from "@/features/auth/usePermissions";
import { fmtDate, isoDate } from "@/lib/format";

import { cabinetApi, type CabinetItem, type MedicinePackage, type PackageStatus } from "./api";
import { DoseCalculator } from "./DoseCalculator";
import { ItemLinks } from "./ItemLinks";
import { CABINET_ITEM_FIELDS, PACKAGE_FIELDS } from "./fields";

const STATUS_COLOR: Record<PackageStatus, string> = {
  expired: "red",
  soon: "orange",
  ok: "teal",
  unknown: "gray",
  finished: "gray",
};

type FilterWho = "all" | "children" | "adults";

export function CabinetPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const canEdit = usePermissions().canEdit("health");
  const [search, setSearch] = useState("");
  const [q] = useDebouncedValue(search, 250);
  const [forWhom, setForWhom] = useState<FilterWho>("all");
  const [showFinished, setShowFinished] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const [itemForm, setItemForm] = useState<CabinetItem | null | "new">(null);

  const items = useQuery({
    queryKey: ["cabinet", q, forWhom, showFinished],
    queryFn: () => cabinetApi.list(q, forWhom, showFinished),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["cabinet"] });
  const deleteItem = useMutation({ mutationFn: cabinetApi.deleteItem, onSuccess: refresh });

  const counts = useMemo(() => {
    const boxes = (items.data ?? []).flatMap((i) => i.packages);
    return {
      expired: boxes.filter((p) => p.status === "expired").length,
      soon: boxes.filter((p) => p.status === "soon").length,
    };
  }, [items.data]);
  const opened = items.data?.find((i) => i.id === openId) ?? null;

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group>
          <Title order={2}>{t("cabinet.title")}</Title>
          {counts.expired > 0 && (
            <Badge color="red" size="lg">
              {t("cabinet.expiredCount", { count: counts.expired })}
            </Badge>
          )}
          {counts.soon > 0 && (
            <Badge color="orange" size="lg">
              {t("cabinet.soonCount", { count: counts.soon })}
            </Badge>
          )}
        </Group>
        {canEdit && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setItemForm("new")}>
            {t("cabinet.addMedicine")}
          </Button>
        )}
      </Group>

      <Group>
        <TextInput
          leftSection={<IconSearch size={16} />}
          placeholder={t("cabinet.search")}
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          w={320}
        />
        <SegmentedControl
          value={forWhom}
          onChange={(v) => setForWhom(v as FilterWho)}
          data={[
            { value: "all", label: t("cabinet.filter.all") },
            { value: "children", label: t("cabinet.filter.children") },
            { value: "adults", label: t("cabinet.filter.adults") },
          ]}
        />
        <Switch
          label={t("cabinet.showFinished")}
          checked={showFinished}
          onChange={(e) => setShowFinished(e.currentTarget.checked)}
        />
      </Group>

      <Paper withBorder p="md">
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t("cabinet.f.name")}</Table.Th>
              <Table.Th>{t("cabinet.f.indications")}</Table.Th>
              <Table.Th>{t("cabinet.f.forWhom")}</Table.Th>
              <Table.Th>{t("cabinet.boxes")}</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(items.data ?? []).map((item) => (
              <Table.Tr key={item.id} onClick={() => setOpenId(item.id)} style={{ cursor: "pointer" }}>
                <Table.Td>
                  <Text fw={600}>{item.name}</Text>
                  <Text size="xs" c="dimmed">
                    {[item.substance, t(`cabinet.form.${item.form}`)].filter(Boolean).join(" · ")}
                  </Text>
                </Table.Td>
                <Table.Td maw={320}>
                  <Text size="sm" lineClamp={2}>
                    {item.indications || "—"}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <WhoBadge item={item} />
                </Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    {item.packages.length ? (
                      item.packages.map((p) => <PackageBadge key={p.id} p={p} />)
                    ) : (
                      <Text size="xs" c="dimmed">
                        {t("cabinet.outOfStock")}
                      </Text>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td onClick={(e) => e.stopPropagation()}>
                  {canEdit && (
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <ActionIcon variant="subtle" onClick={() => setItemForm(item)}>
                        <IconPencil size={16} />
                      </ActionIcon>
                      <Popover withArrow>
                        <Popover.Target>
                          <ActionIcon variant="subtle" color="red" aria-label={t("finance.action.delete")}>
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Popover.Target>
                        <Popover.Dropdown>
                          <Stack gap="xs" maw={240}>
                            <Text size="sm">{t("cabinet.deleteMedicineConfirm")}</Text>
                            <Button size="xs" color="red" onClick={() => deleteItem.mutate(item.id)}>
                              {t("finance.action.delete")}
                            </Button>
                          </Stack>
                        </Popover.Dropdown>
                      </Popover>
                    </Group>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
            {items.isSuccess && !items.data.length && (
              <Table.Tr>
                <Table.Td colSpan={5} ta="center" c="dimmed" py="md">
                  {search ? t("cabinet.noMatches") : t("cabinet.empty")}
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      <ItemDrawer item={opened} canEdit={canEdit} onClose={() => setOpenId(null)} onChanged={refresh} />

      <RecordFormModal
        fields={CABINET_ITEM_FIELDS}
        record={itemForm === "new" ? null : (itemForm as Row | null)}
        opened={itemForm !== null}
        onClose={() => setItemForm(null)}
        onSave={(payload) =>
          cabinetApi.saveItem(payload, itemForm && itemForm !== "new" ? itemForm.id : undefined)
        }
        onSaved={refresh}
        titleKey={{ add: "cabinet.addMedicine", edit: "cabinet.editMedicine" }}
      />
    </Stack>
  );
}

function ageLabel(months: number, t: (k: string, o?: Record<string, unknown>) => string): string {
  return months >= 24 && months % 12 === 0
    ? t("cabinet.fromYears", { count: months / 12 })
    : t("cabinet.fromMonths", { count: months });
}

function WhoBadge({ item }: { item: CabinetItem }) {
  const { t } = useTranslation();
  return (
    <Stack gap={2}>
      <Badge variant="light" color={item.for_whom === "children" ? "pink" : item.for_whom === "adults" ? "indigo" : "gray"}>
        {t(`cabinet.forWhom.${item.for_whom}`)}
      </Badge>
      {item.min_age_months != null && (
        <Text size="xs" c="dimmed">
          {ageLabel(item.min_age_months, t)}
        </Text>
      )}
    </Stack>
  );
}

function PackageBadge({ p }: { p: MedicinePackage }) {
  const { t } = useTranslation();
  return (
    <Tooltip label={t(`cabinet.status.${p.status}`)}>
      <Badge variant="light" color={STATUS_COLOR[p.status]}>
        {p.effective_expiry ? fmtDate(p.effective_expiry) : "?"}
        {p.opened_on ? " · " + t("cabinet.openedShort") : ""}
      </Badge>
    </Tooltip>
  );
}

function ItemDrawer(props: {
  item: CabinetItem | null;
  canEdit: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const { item } = props;
  const [packageForm, setPackageForm] = useState<MedicinePackage | null | "new">(null);
  const quick = useMutation({
    mutationFn: ({ p, patch }: { p: MedicinePackage; patch: Partial<MedicinePackage> }) => {
      const { id, effective_expiry: _e, status: _s, ...rest } = p;
      return cabinetApi.savePackage({ ...rest, ...patch }, { id });
    },
    onSuccess: props.onChanged,
  });
  const remove = useMutation({ mutationFn: cabinetApi.deletePackage, onSuccess: props.onChanged });
  const today = isoDate(new Date());

  return (
    <Drawer opened={!!item} onClose={props.onClose} position="right" size="md" title={item?.name}>
      {item && (
        <Stack>
          {item.substance && <Text c="dimmed">{item.substance}</Text>}
          <Group gap="xs">
            <WhoBadge item={item} />
            <Badge variant="outline">{t(`cabinet.form.${item.form}`)}</Badge>
          </Group>
          <Section label={t("cabinet.f.indications")} text={item.indications} />
          <Section label={t("cabinet.f.dosage")} text={item.dosage_notes} />
          <Section label={t("cabinet.f.notes")} text={item.notes} />
          {(item.dose_mg_per_kg || item.dose_ml_per_kg) && <DoseCalculator item={item} />}
          <ItemLinks itemId={item.id} />

          <Group justify="space-between" mt="md">
            <Title order={5}>{t("cabinet.boxes")}</Title>
            {props.canEdit && (
              <Button size="xs" leftSection={<IconPlus size={14} />} onClick={() => setPackageForm("new")}>
                {t("cabinet.addBox")}
              </Button>
            )}
          </Group>
          {!item.packages.length && (
            <Text size="sm" c="dimmed">
              {t("cabinet.outOfStock")}
            </Text>
          )}
          {item.packages.map((p) => (
            <Paper key={p.id} withBorder p="sm">
              <Group justify="space-between" wrap="nowrap">
                <Stack gap={2}>
                  <Group gap="xs">
                    <PackageBadge p={p} />
                    <Text size="xs" c="dimmed">
                      {t(`cabinet.status.${p.status}`)}
                    </Text>
                  </Group>
                  <Text size="xs" c="dimmed">
                    {[
                      p.expiry_date && t("cabinet.p.printed", { date: fmtDate(p.expiry_date) }),
                      p.opened_on && t("cabinet.p.opened", { date: fmtDate(p.opened_on) }),
                      p.days_after_opening && t("cabinet.p.lasts", { count: p.days_after_opening }),
                      p.location,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </Text>
                </Stack>
                {props.canEdit && (
                  <Group gap={4} wrap="nowrap">
                    {!p.opened_on && !p.finished_on && (
                      <Tooltip label={t("cabinet.openToday")}>
                        <ActionIcon variant="subtle" onClick={() => quick.mutate({ p, patch: { opened_on: today } })}>
                          <IconLockOpen size={16} />
                        </ActionIcon>
                      </Tooltip>
                    )}
                    {!p.finished_on && (
                      <Tooltip label={t("cabinet.finish")}>
                        <ActionIcon
                          variant="subtle"
                          color="gray"
                          onClick={() => quick.mutate({ p, patch: { finished_on: today } })}
                        >
                          <IconCheck size={16} />
                        </ActionIcon>
                      </Tooltip>
                    )}
                    <ActionIcon variant="subtle" onClick={() => setPackageForm(p)}>
                      <IconPencil size={16} />
                    </ActionIcon>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label={t("finance.action.delete")}
                      onClick={() => remove.mutate(p.id)}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                )}
              </Group>
            </Paper>
          ))}

          <RecordFormModal
            fields={PACKAGE_FIELDS}
            record={packageForm === "new" ? null : (packageForm as Row | null)}
            opened={packageForm !== null}
            onClose={() => setPackageForm(null)}
            onSave={(payload) =>
              cabinetApi.savePackage(
                payload,
                packageForm && packageForm !== "new" ? { id: packageForm.id } : { itemId: item.id },
              )
            }
            onSaved={props.onChanged}
            titleKey={{ add: "cabinet.addBox", edit: "cabinet.editBox" }}
          />
        </Stack>
      )}
    </Drawer>
  );
}

function Section({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
        {text}
      </Text>
    </Stack>
  );
}
