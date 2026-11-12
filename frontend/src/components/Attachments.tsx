/**
 * Files attached to any record (test result, note, …): list (open in a new
 * tab), upload (PDF / images, drop or pick — on a phone also the camera),
 * delete. Files are served only through the permission-checked
 * /api/media/<id>/ endpoint; the server decides who may see or add them.
 */
import { ActionIcon, Anchor, Group, Stack, Text } from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { IconFile, IconTrash, IconUpload } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import "@mantine/dropzone/styles.css";

import { fmtDateTime, fmtNumber } from "@/lib/format";

const ACCEPT = ["application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic"];
const MAX_BYTES = 25 * 1024 * 1024;

export type AttachmentInfo = {
  id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
  url: string;
};

function csrf(): string {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? "";
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (method !== "GET") headers.set("X-CSRFToken", csrf());
  const resp = await fetch("/api" + path, { ...init, headers, credentials: "include" });
  if (!resp.ok) throw new Error(`${method} ${path} failed: ${resp.status}`);
  return (await resp.json()) as T;
}

export const attachmentsApi = {
  list: (subjectType: string, subjectId: string) =>
    call<AttachmentInfo[]>(`/attachments?subject_type=${subjectType}&subject_id=${subjectId}`),
  upload: (subjectType: string, subjectId: string, file: File) => {
    const body = new FormData();
    body.append("subject_type", subjectType);
    body.append("subject_id", subjectId);
    body.append("file", file);
    return call<AttachmentInfo>("/attachments", { method: "POST", body });
  },
  remove: (id: string) => call<{ deleted: boolean }>(`/attachments/${id}`, { method: "DELETE" }),
};

export function Attachments(props: {
  /** e.g. "health.testresult", "notes.note" */
  subjectType: string;
  subjectId: string;
  canEdit: boolean;
  /** After an upload / delete (e.g. to refresh a file count). */
  onChanged?: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["attachments", props.subjectType, props.subjectId];
  const files = useQuery({ queryKey: key, queryFn: () => attachmentsApi.list(props.subjectType, props.subjectId) });
  const done = () => {
    qc.invalidateQueries({ queryKey: key });
    props.onChanged?.();
  };
  const upload = useMutation({
    mutationFn: async (list: File[]) => {
      for (const f of list) await attachmentsApi.upload(props.subjectType, props.subjectId, f);
    },
    onSuccess: done,
  });
  const remove = useMutation({ mutationFn: attachmentsApi.remove, onSuccess: done });

  return (
    <Stack gap="xs">
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
      {files.isSuccess && !files.data.length && !props.canEdit && (
        <Text size="sm" c="dimmed">
          {t("health.files.none")}
        </Text>
      )}
      {props.canEdit && (
        <Dropzone onDrop={(list) => upload.mutate(list)} accept={ACCEPT} maxSize={MAX_BYTES} loading={upload.isPending}>
          <Group justify="center" gap="sm" mih={60}>
            <IconUpload size={22} />
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
  );
}
