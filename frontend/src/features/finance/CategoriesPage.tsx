/**
 * Finanse → Kategorie: expense and income categories — add, rename and
 * recolour (built-in ones too), merge one into another (its transactions,
 * repeating payments and bookmarks move), delete an unused one.
 */
import { useState } from "react";
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

type Kind = "expense" | "income";
const SWATCHES = ["#fa5252", "#e64980", "#be4bdb", "#7950f2", "#4c6ef5", "#228be6", "#15aabf", "#12b886", "#40c057", "#82c91e", "#fab005", "#fd7e14", "#868e96"];

export function CategoriesPage() {
  const { t } = useTranslation();
  const canEdit = usePermissions().canEdit("finance");
  const categories = useQuery({ queryKey: ["finance", "categories"], queryFn: () => financeApi.listCategories() });
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
              items={(categories.data ?? []).filter((c) => c.kind === kind).sort((a, b) => a.name.localeCompare(b.name))}
              canEdit={canEdit}
              onEdit={setEditing}
              onMerge={setMerging}
            />
          </Grid.Col>
        ))}
      </Grid>
      <EditModal category={editing} onClose={() => setEditing(null)} />
      <MergeModal category={merging} all={categories.data ?? []} onClose={() => setMerging(null)} />
    </Stack>
  );
}

function useRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["finance"] });
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
  const [name, setName] = useState("");
  const [color, setColor] = useState(props.kind === "income" ? "#12b886" : "#868e96");
  const add = useMutation({
    mutationFn: () => financeApi.createCategory({ name, kind: props.kind, color }),
    onSuccess: () => {
      setName("");
      refresh();
    },
  });
  const remove = useMutation({ mutationFn: financeApi.deleteCategory, onSuccess: refresh });

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
            <TextInput style={{ flex: 1 }} placeholder={t("finance.categories.newName")} value={name} onChange={(e) => setName(e.currentTarget.value)} />
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
          {props.items.map((c) => (
            <Table.Tr key={c.id}>
              <Table.Td w={28}>
                <ColorSwatch color={c.color} size={16} />
              </Table.Td>
              <Table.Td>
                <Group gap={6}>
                  <Text size="sm">{c.name}</Text>
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
              <Table.Td w={110}>
                {props.canEdit && (
                  <Group gap={2} justify="flex-end" wrap="nowrap">
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
                    {!c.is_system && c.used === 0 && (
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
          ))}
        </Table.Tbody>
      </Table>
    </Paper>
  );
}

function EditModal({ category, onClose }: { category: Category | null; onClose: () => void }) {
  const { t } = useTranslation();
  const refresh = useRefresh();
  const [name, setName] = useState("");
  const [color, setColor] = useState("");
  const [shownFor, setShownFor] = useState<string | null>(null);
  if (category && shownFor !== category.id) {
    setShownFor(category.id);
    setName(category.name);
    setColor(category.color);
  }
  const save = useMutation({
    mutationFn: () => financeApi.updateCategory(category!.id, { name, color }),
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
  const options = all.filter((c) => category && c.kind === category.kind && c.id !== category.id);
  return (
    <Modal opened={!!category} onClose={onClose} title={t("finance.categories.mergeTitle", { name: category?.name ?? "" })}>
      <Stack>
        <Text size="sm" c="dimmed">
          {t("finance.categories.mergeHint", { count: category?.used ?? 0 })}
        </Text>
        <Select
          label={t("finance.categories.mergeInto")}
          data={options.map((c) => ({ value: c.id, label: c.name }))}
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
