/**
 * Import transactions from a money app's / bank's export: a CSV, TSV or
 * .xlsx file, or rows pasted from a spreadsheet (with their header). The
 * preview shows the rows, those already here (skipped by default), the
 * lines that couldn't be read, and the categories — created when missing,
 * or pointed at existing ones.
 */
import { useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  FileInput,
  Group,
  Modal,
  Progress,
  ScrollArea,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFileImport } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { Person } from "@/features/people/api";
import { fmtDate, fmtMoney } from "@/lib/format";

import { type Category, financeApi, type ImportCategory, type ImportPreview } from "./api";
import { categoryOptions, PATH_SEP } from "./categoryTree";

const NEW = "new";
const CHUNK = 500; // rows per request (keeps each under the server's body limit)
const SHOWN = 50;

const pathKey = (c: Pick<ImportCategory, "kind" | "category" | "subcategory">) => `${c.kind}|${c.category}|${c.subcategory}`;
const pathLabel = (c: Pick<ImportCategory, "category" | "subcategory">) =>
  c.subcategory ? `${c.category || "Inne"}${PATH_SEP}${c.subcategory}` : c.category || "Inne";

export function ImportModal(props: { opened: boolean; onClose: () => void; categories: Category[]; people: Person[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [pasted, setPasted] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [targets, setTargets] = useState<Record<string, string>>({});
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [personId, setPersonId] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  useEffect(() => {
    if (!props.opened) return;
    setFile(null);
    setPasted("");
    setPreview(null);
    setSkipDuplicates(true);
    setPersonId(null);
  }, [props.opened]);

  const read = useMutation({
    mutationFn: () => financeApi.importPreview(file ?? new File([pasted], "wklejone.tsv", { type: "text/plain" })),
    onSuccess: (p) => {
      setPreview(p);
      setTargets(Object.fromEntries(p.categories.map((c) => [pathKey(c), c.match_id ?? NEW])));
    },
  });
  const rows = (preview?.rows ?? []).filter((r) => !(skipDuplicates && r.duplicate));
  const run = useMutation({
    mutationFn: async () => {
      const categories = (preview?.categories ?? []).map((c) => ({
        kind: c.kind,
        category: c.category,
        subcategory: c.subcategory,
        target_id: targets[pathKey(c)] === NEW ? null : targets[pathKey(c)],
      }));
      const done = { created: 0, categories: 0 };
      for (let i = 0; i < rows.length; i += CHUNK) {
        setProgress(i / rows.length);
        try {
          const r = await financeApi.importRows({ rows: rows.slice(i, i + CHUNK), categories, person_id: personId });
          done.created += r.created;
          done.categories += r.categories;
        } catch (e) {
          throw new Error(t("finance.import.partly", { count: done.created, total: rows.length, error: (e as Error).message }));
        }
      }
      return done;
    },
    onSuccess: (r) => {
      notifications.show({ message: t("finance.import.done", { count: r.created, categories: r.categories }) });
      props.onClose();
    },
    onSettled: () => {
      setProgress(null);
      qc.invalidateQueries({ queryKey: ["finance"] });
    },
  });

  const readError = read.error ? t(`finance.import.error.${read.error.message}`, { defaultValue: read.error.message }) : null;
  const duplicates = (preview?.rows ?? []).filter((r) => r.duplicate).length;
  // Opis is the name (Notatka goes to the notes; it's the name when there's no Opis).
  const name = (r: { note: string; description: string }) => r.description.trim() || r.note || "—";

  return (
    <Modal opened={props.opened} onClose={props.onClose} title={t("finance.import.title")} size="xl">
      {!preview ? (
        <Stack>
          <Text size="sm" c="dimmed">
            {t("finance.import.formatHint")}
          </Text>
          <FileInput
            label={t("finance.import.file")}
            accept=".csv,.tsv,.txt,.xlsx,.xls"
            clearable
            value={file}
            onChange={setFile}
            leftSection={<IconFileImport size={16} />}
          />
          <Textarea
            label={t("finance.import.paste")}
            placeholder={"Data\tCategory\tPodkategorie\tNotatka\tPLN\tIncome/Expense\t…"}
            autosize
            minRows={4}
            maxRows={10}
            disabled={!!file}
            value={pasted}
            onChange={(e) => setPasted(e.currentTarget.value)}
            styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 12 } }}
          />
          {readError && <Alert color="red">{readError}</Alert>}
          <Group justify="flex-end">
            <Button onClick={() => read.mutate()} loading={read.isPending} disabled={!file && !pasted.trim()}>
              {t("finance.import.read")}
            </Button>
          </Group>
        </Stack>
      ) : (
        <Stack>
          <Group gap="xs">
            <Badge size="lg" variant="light">
              {t("finance.import.toImport", { count: rows.length })}
            </Badge>
            {duplicates > 0 && (
              <Badge size="lg" variant="light" color="gray">
                {t("finance.import.duplicates", { count: duplicates })}
              </Badge>
            )}
            {preview.skipped.length > 0 && (
              <Badge size="lg" variant="light" color="orange">
                {t("finance.import.skipped", { count: preview.skipped.length })}
              </Badge>
            )}
          </Group>
          {duplicates > 0 && (
            <Switch label={t("finance.import.skipDuplicates")} checked={skipDuplicates} onChange={(e) => setSkipDuplicates(e.currentTarget.checked)} />
          )}
          {preview.skipped.length > 0 && (
            <Alert color="orange" variant="light" p="xs">
              <Stack gap={2}>
                {preview.skipped.slice(0, 8).map((s) => (
                  <Text key={s.line} size="xs">
                    {t("finance.import.skippedLine", { line: s.line, reason: t(`finance.import.reason.${s.reason}`), text: s.text })}
                  </Text>
                ))}
                {preview.skipped.length > 8 && (
                  <Text size="xs" c="dimmed">
                    {t("finance.import.more", { count: preview.skipped.length - 8 })}
                  </Text>
                )}
              </Stack>
            </Alert>
          )}

          <Select
            label={t("finance.field.forWhom")}
            placeholder={t("finance.field.forWhomShared")}
            clearable
            data={props.people.map((p) => ({ value: p.id, label: p.display_name }))}
            value={personId}
            onChange={setPersonId}
            maw={320}
          />

          <Stack gap={6}>
            <Text size="sm" fw={600}>
              {t("finance.import.categories")}
            </Text>
            <Text size="xs" c="dimmed">
              {t("finance.import.categoriesHint")}
            </Text>
            {preview.categories.map((c) => {
              const key = pathKey(c);
              const options = categoryOptions(props.categories.filter((cat) => cat.kind === c.kind), props.categories);
              return (
                <Group key={key} justify="space-between" wrap="nowrap" gap="xs">
                  <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                    <Badge size="xs" variant="light" color={c.kind === "income" ? "teal" : "red"}>
                      {t(`finance.chart.${c.kind}`)}
                    </Badge>
                    <Text size="sm" truncate>
                      {pathLabel(c)}
                    </Text>
                    <Text size="xs" c="dimmed">
                      ×{c.count}
                    </Text>
                  </Group>
                  <Select
                    w={280}
                    size="xs"
                    searchable
                    allowDeselect={false}
                    data={[...(c.match_id ? [] : [{ value: NEW, label: t("finance.import.create", { path: pathLabel(c) }) }]), ...options]}
                    value={targets[key] ?? NEW}
                    onChange={(v) => setTargets((m) => ({ ...m, [key]: v ?? NEW }))}
                  />
                </Group>
              );
            })}
          </Stack>

          <ScrollArea.Autosize mah={260}>
            <Table fz="xs" verticalSpacing={4}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("finance.field.date")}</Table.Th>
                  <Table.Th>{t("finance.field.name")}</Table.Th>
                  <Table.Th>{t("finance.field.category")}</Table.Th>
                  <Table.Th ta="right">{t("finance.field.amount")}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {preview.rows.slice(0, SHOWN).map((r) => (
                  <Table.Tr key={r.line} c={r.duplicate && skipDuplicates ? "dimmed" : undefined}>
                    <Table.Td>{fmtDate(r.date)}</Table.Td>
                    <Table.Td>
                      {name(r)}
                      {r.duplicate && (
                        <Badge size="xs" variant="outline" color="gray" ml={6}>
                          {t("finance.import.duplicate")}
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td>{pathLabel(r)}</Table.Td>
                    <Table.Td ta="right" c={r.kind === "income" ? "teal" : undefined}>
                      {fmtMoney(r.amount, r.currency)}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            {preview.rows.length > SHOWN && (
              <Text size="xs" c="dimmed" mt={4}>
                {t("finance.import.more", { count: preview.rows.length - SHOWN })}
              </Text>
            )}
          </ScrollArea.Autosize>

          {progress != null && <Progress value={progress * 100} animated />}
          {run.isError && <Alert color="red">{(run.error as Error).message}</Alert>}
          <Group justify="space-between">
            <Button variant="default" onClick={() => setPreview(null)} disabled={run.isPending}>
              {t("finance.import.back")}
            </Button>
            <Button onClick={() => run.mutate()} loading={run.isPending} disabled={!rows.length}>
              {t("finance.import.run", { count: rows.length })}
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
