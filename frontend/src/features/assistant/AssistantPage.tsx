/** Asystent — your conversations (private to you) and the chat.
 *  "/assistant?c=<id>" opens a conversation (e.g. from the chat button). */
import { useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Grid,
  Group,
  NavLink,
  Paper,
  Popover,
  ScrollArea,
  Stack,
  Text,
} from "@mantine/core";
import { IconLock, IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";

import { fmtDateTime } from "@/lib/format";

import { ASSISTANT_KEY, assistantApi } from "./api";
import { ChatPanel } from "./ChatPanel";

export function AssistantPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [fresh, setFresh] = useState(0); // remount the panel for "new conversation"
  const conversations = useQuery({
    queryKey: [...ASSISTANT_KEY, "conversations"],
    queryFn: assistantApi.conversations,
  });
  const selectedId = params.get("c");
  const selected = conversations.data?.find((c) => c.id === selectedId) ?? null;
  const select = (id: string | null) => setParams(id ? { c: id } : {}, { replace: true });
  // The panel that started a conversation keeps showing it, with its pending
  // message and "thinking…" (a new panel would lose them); picking another
  // conversation, or "new", gives a fresh panel.
  const [startedId, setStartedId] = useState<string | null>(null);
  const panelKey = selectedId && selectedId !== startedId ? selectedId : `new-${fresh}`;
  const remove = useMutation({
    mutationFn: assistantApi.deleteConversation,
    onSuccess: (_, id) => {
      if (id === selectedId) select(null);
      qc.invalidateQueries({ queryKey: [...ASSISTANT_KEY, "conversations"] });
    },
  });

  return (
    <Stack gap="md">
      <PageHeader
        title={t("assistant.title")}
        subtitle={t("page.assistant.subtitle")}
        actions={
          <Button
            leftSection={<IconPlus size={16} />}
            variant="light"
            onClick={() => {
              select(null);
              setStartedId(null);
              setFresh((n) => n + 1);
            }}
          >
            {t("assistant.new")}
          </Button>
        }
      />
      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper withBorder p="xs">
            <ScrollArea.Autosize mah="calc(100vh - 220px)">
              {(conversations.data ?? []).map((c) => (
                <NavLink
                  key={c.id}
                  active={c.id === selectedId}
                  onClick={() => select(c.id)}
                  label={
                    <Group gap={4} wrap="nowrap">
                      {c.private && <IconLock size={12} />}
                      <Text size="sm" truncate>
                        {c.title || t("assistant.untitled")}
                      </Text>
                    </Group>
                  }
                  description={fmtDateTime(c.updated_at)}
                  rightSection={
                    <Popover withArrow>
                      <Popover.Target>
                        <ActionIcon variant="subtle" color="gray" size="sm" onClick={(e) => e.stopPropagation()} aria-label={t("finance.action.delete")}>
                          <IconTrash size={14} />
                        </ActionIcon>
                      </Popover.Target>
                      <Popover.Dropdown onClick={(e) => e.stopPropagation()}>
                        <Stack gap="xs" maw={220}>
                          <Text size="sm">{t("assistant.deleteConfirm")}</Text>
                          <Button size="xs" color="red" onClick={() => remove.mutate(c.id)}>
                            {t("finance.action.delete")}
                          </Button>
                        </Stack>
                      </Popover.Dropdown>
                    </Popover>
                  }
                />
              ))}
              {conversations.isSuccess && !conversations.data.length && (
                <Text size="sm" c="dimmed" p="sm">
                  {t("assistant.noConversations")}
                </Text>
              )}
            </ScrollArea.Autosize>
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper withBorder p="sm">
            {selected?.private && (
              <Badge leftSection={<IconLock size={10} />} variant="light" color="teal" mb="xs">
                {t("assistant.privateBadge")}
              </Badge>
            )}
            <ChatPanel
              key={panelKey}
              conversation={selected}
              onStarted={(c) => {
                setStartedId(c.id);
                qc.invalidateQueries({ queryKey: [...ASSISTANT_KEY, "conversations"] });
                select(c.id);
              }}
              height="calc(100vh - 230px)"
            />
          </Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
