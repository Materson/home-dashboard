/**
 * One conversation: messages, proposed-change cards, "what was sent", and
 * the input (Enter sends, Shift+Enter new line, attach photos / PDFs — on a
 * phone the picker offers the camera). The page you're on goes along with
 * each question, so "this car" / "her" make sense to the assistant.
 * Used on the Asystent page and in the chat button's drawer.
 */
import { useEffect, useRef, useState } from "react";
import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Box,
  CloseButton,
  FileButton,
  Group,
  Image,
  Loader,
  Paper,
  ScrollArea,
  Stack,
  Switch,
  Text,
  Textarea,
  Tooltip,
} from "@mantine/core";
import { IconLock, IconPaperclip, IconSend } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";

import { ActionCard, CHANGED_KEYS } from "./ActionCard";
import { type Conversation, type Message, ASSISTANT_KEY, assistantApi } from "./api";
import { CallsModal } from "./CallsModal";

const ACCEPT = "image/jpeg,image/png,image/webp,application/pdf";

export function ChatPanel(props: {
  conversation: Conversation | null;
  /** A new conversation was started by sending the first message. */
  onStarted: (c: Conversation) => void;
  height: string | number;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const page = useLocation().pathname;
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isPrivate, setPrivate] = useState(false);
  const [sending, setSending] = useState<{ text: string; files: File[] } | null>(null);
  const [callsFor, setCallsFor] = useState<string | null>(null);
  const viewport = useRef<HTMLDivElement>(null);

  const status = useQuery({ queryKey: [...ASSISTANT_KEY, "status"], queryFn: assistantApi.status, staleTime: 60_000 });
  // Started here (first message) until the parent shows it as selected.
  const [started, setStarted] = useState<Conversation | null>(null);
  const conv = props.conversation ?? started;
  const messagesKey = [...ASSISTANT_KEY, "messages", conv?.id];
  const messages = useQuery({
    queryKey: messagesKey,
    queryFn: () => assistantApi.messages(conv!.id),
    enabled: !!conv,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: messagesKey });

  const send = useMutation({
    mutationFn: async (v: { text: string; files: File[] }) => {
      let target = conv;
      if (!target) {
        target = await assistantApi.createConversation(isPrivate || !status.data?.configured);
        setStarted(target);
        props.onStarted(target);
      }
      const result = await assistantApi.send(target.id, v.text, page, v.files);
      return { target, result };
    },
    onMutate: (v) => setSending(v),
    onSettled: () => setSending(null),
    onSuccess: ({ target, result }) => {
      // The list may have been reloaded meanwhile (e.g. back to the tab): no doubles.
      const added = new Set([result.question.id, result.answer.id]);
      qc.setQueryData<Message[]>([...ASSISTANT_KEY, "messages", target.id], (old) => [
        ...(old ?? []).filter((m) => !added.has(m.id)),
        result.question,
        result.answer,
      ]);
      qc.invalidateQueries({ queryKey: [...ASSISTANT_KEY, "conversations"] });
      // Confirmed/auto changes touch other pages' data.
      if (result.answer.actions.length) {
        for (const key of CHANGED_KEYS) {
          qc.invalidateQueries({ queryKey: key });
        }
      }
    },
  });

  const submit = () => {
    if ((!text.trim() && !files.length) || send.isPending) return;
    send.mutate({ text: text.trim(), files });
    setText("");
    setFiles([]);
  };

  const list = messages.data ?? [];
  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: "smooth" });
  }, [list.length, sending]);

  const s = status.data;
  if (s && !s.can_use) {
    return <Alert color="gray">{t("assistant.noAccess")}</Alert>;
  }
  if (s && !s.configured && !s.private_available) {
    return (
      <Alert color="yellow" title={t("assistant.notConfigured")}>
        {s.can_manage ? (
          <Anchor component={Link} to="/settings">
            {t("assistant.goToSettings")}
          </Anchor>
        ) : (
          t("assistant.askAdmin")
        )}
      </Alert>
    );
  }
  // Only a local model configured → every new conversation is private.
  const privateConv = conv ? conv.private : isPrivate || !s?.configured;
  const model = privateConv ? s?.local_profile : s?.chat_profile;

  return (
    <Stack gap="xs" h={props.height}>
      <Group justify="space-between" wrap="nowrap">
        {model && (
          <Group gap={6} wrap="nowrap">
            <Badge size="sm" variant="light" color={model.location === "cloud" ? "orange" : "teal"}>
              {t(`assistant.location.${model.location}`)}
            </Badge>
            <Text size="xs" c="dimmed" truncate>
              {model.name}
            </Text>
          </Group>
        )}
        {!conv && s?.private_available && (
          <Switch
            size="xs"
            label={t("assistant.private")}
            checked={isPrivate || !s.configured}
            disabled={!s.configured}
            onChange={(e) => setPrivate(e.currentTarget.checked)}
            thumbIcon={<IconLock size={10} />}
          />
        )}
      </Group>

      <ScrollArea style={{ flex: 1 }} viewportRef={viewport} type="auto">
        <Stack gap="sm" pr="xs">
          {!list.length && !sending && (
            <Text size="sm" c="dimmed" ta="center" mt="lg">
              {t("assistant.empty")}
            </Text>
          )}
          {list.map((m) => (
            <Bubble key={m.id} m={m} onChanged={refresh} onShowCalls={() => setCallsFor(m.id)} />
          ))}
          {sending && (
            <>
              <Bubble
                m={{ id: "pending", role: "user", text: sending.text, error: false, created_at: "", files: [], actions: [], has_calls: false }}
                pendingFiles={sending.files}
              />
              <Group gap="xs">
                <Loader size="xs" type="dots" />
                <Text size="sm" c="dimmed">
                  {t("assistant.thinking")}
                </Text>
              </Group>
            </>
          )}
          {send.isError && <Alert color="red">{(send.error as Error).message}</Alert>}
        </Stack>
      </ScrollArea>

      {files.length > 0 && (
        <Group gap={6}>
          {files.map((f, i) => (
            <Badge key={i} variant="light" rightSection={<CloseButton size="xs" onClick={() => setFiles((l) => l.filter((_, j) => j !== i))} />}>
              {f.name}
            </Badge>
          ))}
        </Group>
      )}
      <Group gap="xs" wrap="nowrap" align="flex-end">
        <FileButton onChange={(picked) => setFiles((l) => [...l, ...picked].slice(0, 4))} accept={ACCEPT} multiple>
          {(fp) => (
            <Tooltip label={t("assistant.attach")}>
              <ActionIcon {...fp} variant="light" size="lg" aria-label={t("assistant.attach")}>
                <IconPaperclip size={18} />
              </ActionIcon>
            </Tooltip>
          )}
        </FileButton>
        <Textarea
          style={{ flex: 1 }}
          autosize
          minRows={1}
          maxRows={6}
          placeholder={t("assistant.placeholder")}
          value={text}
          onChange={(e) => setText(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <ActionIcon size="lg" onClick={submit} loading={send.isPending} disabled={!text.trim() && !files.length} aria-label={t("assistant.send")}>
          <IconSend size={18} />
        </ActionIcon>
      </Group>
      <CallsModal messageId={callsFor} onClose={() => setCallsFor(null)} />
    </Stack>
  );
}

function Bubble(props: { m: Message; pendingFiles?: File[]; onChanged?: () => void; onShowCalls?: () => void }) {
  const { t } = useTranslation();
  const { m } = props;
  const mine = m.role === "user";
  return (
    <Stack gap={6} align={mine ? "flex-end" : "flex-start"}>
      {(m.files.length > 0 || (props.pendingFiles?.length ?? 0) > 0) && (
        <Group gap={6} justify={mine ? "flex-end" : "flex-start"}>
          {m.files.map((f) =>
            f.mime_type.startsWith("image/") ? (
              <Anchor key={f.id} href={f.url} target="_blank" rel="noopener">
                <Image src={f.url} h={90} w="auto" radius="sm" alt={f.original_name} />
              </Anchor>
            ) : (
              <Anchor key={f.id} href={f.url} target="_blank" rel="noopener" size="sm">
                {f.original_name}
              </Anchor>
            ),
          )}
          {props.pendingFiles?.map((f, i) => (
            <Badge key={i} variant="light">
              {f.name}
            </Badge>
          ))}
        </Group>
      )}
      {m.text && (
        <Paper
          px="sm"
          py={6}
          radius="md"
          maw="85%"
          bg={mine ? "var(--mantine-primary-color-light)" : m.error ? "var(--mantine-color-red-light)" : "var(--mantine-color-default-hover)"}
        >
          <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
            {m.text}
          </Text>
        </Paper>
      )}
      {m.actions.map((a) => (
        <Box key={a.id} w="85%" maw={420}>
          <ActionCard action={a} onChanged={() => props.onChanged?.()} />
        </Box>
      ))}
      {m.has_calls && (
        <Anchor size="xs" c="dimmed" onClick={props.onShowCalls}>
          {t("assistant.sent.link")}
        </Anchor>
      )}
    </Stack>
  );
}
