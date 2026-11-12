/**
 * Finanse → Kategorie: expense and income categories in two levels — main
 * ones (Samochód, Zdrowie) and their sub-categories (Paliwo, Leki). Add one
 * (straight under a main one with its "+"), rename, recolour and move it under
 * another main one (built-in ones too), merge one into another (its
 * transactions, repeating payments and bookmarks move), delete an unused one.
 */
import { useRef, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  ColorInput,
  ColorSwatch,
  Grid,
  Group,
  Modal,
  Paper,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconArrowMerge, IconPencil, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { usePermissions } from "@/features/auth/usePermissions";

import { type Category, financeApi } from "./api";
import { categoryOptions, treeOrder } from "./categoryTree";
import { renderCategoryOption } from "./CategoryOption";

type Kind = "expense" | "income";
const SWATCHES = ["#fa5252", "#e64980", "#be4bdb", "#7950f2", "#4c6ef5", "#228be6", "#15aabf", "#12b886", "#40c057", "#82c91e", "#fab005", "#fd7e14", "#868e96"];

export function CategoriesPage() {
  const { t } = useTranslation();
  const canEdit = usePermissions().canEdit("finance");
  const categories = useQuery({ queryKey: ["finance", "categories"], queryFn: () => financeApi.listCategories() });
  const all = categories.data ?? [];
  const [editing, setEditing] = useState<Category | null>(null);
  const [merging, setMerging] = useState<Category | null>(null);

  return (
    <Stack gap="lg">
      <Title order={2}>{t("finance.categories.title")}</Title>
      <Grid>
        {(["expense", "income"] as Kind[]).map((kind) => (
          <Grid.Col key={kind} span={{ base: 12, md: 6 }}>
            <KindColumn
              kind={kind}
              items={all.filter((c) => c.kind === kind)}
              canEdit={canEdit}
              onEdit={setEditing}
              onMerge={setMerging}
            />
          </Grid.Col>
        ))}
      </Grid>
      <EditModal category={editing} all={all} onClose={() => setEditing(null)} />
      <MergeModal category={merging} all={all} onClose={() => setMerging(null)} />
    </Stack>
  );
}

function useRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["finance"] });
}

/** Main categories of ``kind`` a category could be put under. */
function mainOptions(all: Category[], kind: string, except?: string) {
  return all
    .filter((c) => c.kind === kind && !c.parent_id && c.id !== except)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((c) => ({ value: c.id, label: c.name }));
}

function KindColumn(props: {
  kind: Kind;
  items: Category[];
  canEdit: boolean;
  onEdit: (c: Category) => void;
  onMerge: (c: Category) => void;
}) {
  const { t } = useTranslation();
  const refresh = useRefresh();
  const nameInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [color, setColor] = useState(props.kind === "income" ? "#12b886" : "#868e96");
  const [parentId, setParentId] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () => financeApi.createCategory({ name, kind: props.kind, color, parent_id: parentId }),
    onSuccess: () => {
      setName("");
      refresh();
    },
  });
  const remove = useMutation({ mutationFn: financeApi.deleteCategory, onSuccess: refresh });
  const hasChildren = new Set(props.items.map((c) => c.parent_id).filter(Boolean));

  function pickParent(id: string | null) {
    setParentId(id);
    const parent = props.items.find((c) => c.id === id);
    if (parent) setColor(parent.color); // a sub-category starts in its main one's colour
  }

  return (
    <Paper withBorder p="md">
      <Title order={4} mb="sm">
        {t(`finance.kind.${props.kind}`)}
      </Title>
      {props.canEdit && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) add.mutate();
          }}
        >
          <Group gap="xs" wrap="nowrap" mb="sm">
            <ColorInput w={56} withPicker={false} withPreview swatches={SWATCHES} swatchesPerRow={7} value={color} onChange={setColor} styles={{ input: { color: "transparent" } }} />
            <TextInput
              ref={nameInput}
              style={{ flex: 1 }}
              placeholder={t(parentId ? "finance.categories.newSubName" : "finance.categories.newName")}
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
            />
            <Select
              w={170}
              placeholder={t("finance.categories.asMain")}
              aria-label={t("finance.categories.parent")}
              data={mainOptions(props.items, props.kind)}
              value={parentId}
              onChange={pickParent}
              clearable
              searchable
            />
            <ActionIcon type="submit" size="lg" disabled={!name.trim()} loading={add.isPending} aria-label={t("finance.categories.add")}>
              <IconPlus size={18} />
            </ActionIcon>
          </Group>
          {add.isError && (
            <Alert color="red" mb="sm" p="xs">
              {(add.error as Error).message}
            </Alert>
          )}
        </form>
      )}
      <Table verticalSpacing={4}>
        <Table.Tbody>
          {treeOrder(props.items).map((c) => {
            const isSub = !!c.parent_id;
            return (
              <Table.Tr key={c.id}>
                <Table.Td w={isSub ? 52 : 28} pl={isSub ? 32 : undefined}>
                  <ColorSwatch color={c.color} size={isSub ? 12 : 16} />
                </Table.Td>
                <Table.Td>
                  <Group gap={6}>
                    <Text size="sm" fw={isSub ? undefined : 600}>
                      {c.name}
                    </Text>
                    {c.is_system && (
                      <Badge size="xs" variant="light" color="gray">
                        {t("finance.categories.builtIn")}
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td ta="right">
                  <Text size="xs" c="dimmed">
                    {t("finance.categories.used", { count: c.used })}
                  </Text>
                </Table.Td>
                <Table.Td w={136}>
                  {props.canEdit && (
                    <Group gap={2} justify="flex-end" wrap="nowrap">
                      {!isSub && (
                        <Tooltip label={t("finance.categories.addSub")}>
                          <ActionIcon
                            variant="subtle"
                            onClick={() => {
                              pickParent(c.id);
                              nameInput.current?.focus();
                            }}
                          >
                            <IconPlus size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}
                      <Tooltip label={t("finance.action.edit")}>
                        <ActionIcon variant="subtle" onClick={() => props.onEdit(c)}>
                          <IconPencil size={16} />
                        </ActionIcon>
                      </Tooltip>
                      {!c.is_system && (
                        <Tooltip label={t("finance.categories.merge")}>
                          <ActionIcon variant="subtle" onClick={() => props.onMerge(c)}>
                            <IconArrowMerge size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}
                      {!c.is_system && c.used === 0 && !hasChildren.has(c.id) && (
                        <Tooltip label={t("finance.action.delete")}>
                          <ActionIcon variant="subtle" color="red" loading={remove.isPending && remove.variables === c.id} onClick={() => remove.mutate(c.id)}>
                            <IconTrash size={16} />
                          </ActionIcon>
                        </Tooltip>
                      )}
                    </Group>
                  )}
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
      {remove.isError && (
        <Alert color="red" mt="sm" p="xs">
          {(remove.error as Error).message}
        </Alert>
      )}
    </Paper>
  );
}

function EditModal({ category, all, onClose }: { category: Category | null; all: Category[]; onClose: () => void }) {
  const { t } = useTranslation();
  const refresh = useRefresh();
  const [name, setName] = useState("");
  const [color, setColor] = useState("");
  const [parentId, setParentId] = useState<string | null>(null);
  const [shownFor, setShownFor] = useState<string | null>(null);
  if (category && shownFor !== category.id) {
    setShownFor(category.id);
    setName(category.name);
    setColor(category.color);
    setParentId(category.parent_id);
  }
  // A main category with sub-categories of its own stays a main one (two levels).
  const hasChildren = !!category && all.some((c) => c.parent_id === category.id);
  const save = useMutation({
    mutationFn: () => financeApi.updateCategory(category!.id, { name, color, parent_id: parentId }),
    onSuccess: () => {
      refresh();
      onClose();
      setShownFor(null);
    },
  });
  return (
    <Modal opened={!!category} onClose={() => { onClose(); setShownFor(null); }} title={t("finance.categories.edit")}>
      <Stack>
        <TextInput label={t("finance.field.name")} value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Select
          label={t("finance.categories.parent")}
          placeholder={t("finance.categories.asMain")}
          description={hasChildren ? t("finance.categories.hasSubHint") : undefined}
          data={category ? mainOptions(all, category.kind, category.id) : []}
          value={parentId}
          onChange={setParentId}
          disabled={hasChildren}
          clearable
          searchable
        />
        <ColorInput label={t("finance.categories.color")} swatches={SWATCHES} value={color} onChange={setColor} />
        {save.isError && <Alert color="red">{(save.error as Error).message}</Alert>}
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!name.trim()}>
          {t("finance.action.saveChanges")}
        </Button>
      </Stack>
    </Modal>
  );
}

function MergeModal({ category, all, onClose }: { category: Category | null; all: Category[]; onClose: () => void }) {
  const { t } = useTranslation();
  const refresh = useRefresh();
  const [into, setInto] = useState<string | null>(null);
  const merge = useMutation({
    mutationFn: () => financeApi.mergeCategory(category!.id, into!),
    onSuccess: () => {
      refresh();
      setInto(null);
      onClose();
    },
  });
  // Its sub-categories come along, so a main one with some merges into a main one.
  const hasChildren = !!category && all.some((c) => c.parent_id === category.id);
  const targets = all.filter(
    (c) => category && c.kind === category.kind && c.id !== category.id && !(hasChildren && c.parent_id),
  );
  return (
    <Modal opened={!!category} onClose={onClose} title={t("finance.categories.mergeTitle", { name: category?.name ?? "" })}>
      <Stack>
        <Text size="sm" c="dimmed">
          {t("finance.categories.mergeHint", { count: category?.used ?? 0 })}
          {hasChildren && ` ${t("finance.categories.mergeSubHint")}`}
        </Text>
        <Select
          label={t("finance.categories.mergeInto")}
          data={categoryOptions(targets, all)}
          renderOption={renderCategoryOption}
          value={into}
          onChange={setInto}
          searchable
        />
        {merge.isError && <Alert color="red">{(merge.error as Error).message}</Alert>}
        <Button color="orange" onClick={() => merge.mutate()} loading={merge.isPending} disabled={!into}>
          {t("finance.categories.merge")}
        </Button>
      </Stack>
    </Modal>
  );
}
