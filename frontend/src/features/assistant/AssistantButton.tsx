/** The chat button in the corner of every page: opens the assistant in a
 *  side panel that knows which page you're on. The conversation stays
 *  while you move between pages; "Nowa" starts another, ⤢ opens it full. */
import { useState } from "react";
import { ActionIcon, Affix, Drawer, Group, Text, Tooltip } from "@mantine/core";
import { IconArrowsMaximize, IconMessageChatbot, IconPlus } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";

import { ASSISTANT_KEY, assistantApi, type Conversation } from "./api";
import { ChatPanel } from "./ChatPanel";

export function AssistantButton() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const path = useLocation().pathname;
  const [opened, setOpened] = useState(false);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [fresh, setFresh] = useState(0);
  const status = useQuery({ queryKey: [...ASSISTANT_KEY, "status"], queryFn: assistantApi.status, staleTime: 60_000 });

  const s = status.data;
  if (!s?.can_use || (!s.configured && !s.private_available) || path.startsWith("/assistant")) return null;

  return (
    <>
      {/* above the phone's bottom bar (its height is 0 when hidden) */}
      <Affix position={{ bottom: "calc(var(--app-shell-footer-offset, 0rem) + 20px)", right: 20 }}>
        <Tooltip label={t("assistant.title")} position="left">
          <ActionIcon
            size={52}
            radius="xl"
            variant="gradient"
            gradient={{ from: "indigo.5", to: "violet.5", deg: 135 }}
            style={{ boxShadow: "var(--mantine-shadow-lg)" }}
            onClick={() => setOpened(true)}
            aria-label={t("assistant.title")}
          >
            <IconMessageChatbot size={28} />
          </ActionIcon>
        </Tooltip>
      </Affix>
      <Drawer
        opened={opened}
        onClose={() => setOpened(false)}
        position="right"
        size="md"
        title={
          <Group gap="xs">
            <Text fw={600}>{t("assistant.title")}</Text>
            <Tooltip label={t("assistant.new")}>
              <ActionIcon
                variant="subtle"
                size="sm"
                onClick={() => {
                  setConversation(null);
                  setFresh((n) => n + 1);
                }}
              >
                <IconPlus size={16} />
              </ActionIcon>
            </Tooltip>
            {conversation && (
              <Tooltip label={t("assistant.openFull")}>
                <ActionIcon
                  variant="subtle"
                  size="sm"
                  component={Link}
                  to={`/assistant?c=${conversation.id}`}
                  onClick={() => setOpened(false)}
                >
                  <IconArrowsMaximize size={16} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
        }
      >
        <ChatPanel
          key={conversation?.id ?? `new-${fresh}`}
          conversation={conversation}
          onStarted={(c) => {
            setConversation(c);
            qc.invalidateQueries({ queryKey: [...ASSISTANT_KEY, "conversations"] });
          }}
          height="calc(100vh - 90px)"
        />
      </Drawer>
    </>
  );
}
