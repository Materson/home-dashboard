/**
 * Files of one test result: list (open in a new tab), upload (PDF/images),
 * delete. Files are served only through the permission-checked
 * /api/media/<id>/ endpoint.
 */
import { ActionIcon, Anchor, Group, Modal, Stack, Text } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { IconFile, IconTrash, IconUpload } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import "@mantine/dropzone/styles.css";

import { fmtDateTime, fmtNumber } from "@/lib/format";

import { healthApi } from "./api";

const ACCEPT = ["application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic"];
const MAX_BYTES = 25 * 1024 * 1024;

export function ResultFiles(props: {
  resultId: string | null;
  title: string;
  canEdit: boolean;
  onClose: () => void;
  /** Called after files change so the table's file count refreshes. */
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["health", "files", props.resultId];
  const files = useQuery({
    queryKey: key,
    queryFn: () => healthApi.files(props.resultId!),
    enabled: !!props.resultId,
  });
  const done = () => {
    qc.invalidateQueries({ queryKey: key });
    props.onChanged();
  };
  const upload = useMutation({
    mutationFn: async (list: File[]) => {
      for (const f of list) await healthApi.upload(props.resultId!, f);
    },
    onSuccess: done,
  });
  const remove = useMutation({ mutationFn: (id: string) => healthApi.deleteFile(id), onSuccess: done });

  return (
    <Modal opened={!!props.resultId} onClose={props.onClose} title={props.title} size="lg">
      <Stack>
        {(files.data ?? []).map((f) => (
          <Group key={f.id} justify="space-between" wrap="nowrap">
            <Group gap="xs" wrap="nowrap">
              <IconFile size={18} />
              <Anchor href={f.url} target="_blank" rel="noopener">
                {f.original_name}
              </Anchor>
              <Text size="xs" c="dimmed">
                {fmtNumber(f.size_bytes / 1024)} kB · {fmtDateTime(f.created_at)}
              </Text>
            </Group>
            {props.canEdit && (
              <ActionIcon
                variant="subtle"
                color="red"
                aria-label={t("finance.action.delete")}
                onClick={() => remove.mutate(f.id)}
              >
                <IconTrash size={16} />
              </ActionIcon>
            )}
          </Group>
        ))}
        {files.isSuccess && !files.data.length && (
          <Text size="sm" c="dimmed">
            {t("health.files.none")}
          </Text>
        )}
        {props.canEdit && (
          <Dropzone
            onDrop={(list) => upload.mutate(list)}
            accept={ACCEPT}
            maxSize={MAX_BYTES}
            loading={upload.isPending}
          >
            <Group justify="center" gap="sm" mih={80}>
              <IconUpload size={24} />
              <Stack gap={0}>
                <Text size="sm">{t("health.files.drop")}</Text>
                <Text size="xs" c="dimmed">
                  {t("health.files.limits")}
                </Text>
              </Stack>
            </Group>
          </Dropzone>
        )}
        {upload.isError && (
          <Text size="sm" c="red">
            {t("health.files.failed")}
          </Text>
        )}
      </Stack>
    </Modal>
  );
}
