/** "Co wysłano": exactly what went to the model(s) for one answer — which
 *  provider, cloud or local, which modules' data, and the text as sent
 *  (with aliases instead of names). */
import { Badge, Code, Group, Modal, ScrollArea, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { fmtDateTime } from "@/lib/format";

import { assistantApi } from "./api";

export function CallsModal({ messageId, onClose }: { messageId: string | null; onClose: () => void }) {
  const { t } = useTranslation();
  const calls = useQuery({
    queryKey: ["assistant", "calls", messageId],
    queryFn: () => assistantApi.calls(messageId!),
    enabled: !!messageId,
  });

  return (
    <Modal opened={!!messageId} onClose={onClose} size="xl" title={t("assistant.sent.title")}>
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          {t("assistant.sent.hint")}
        </Text>
        {(calls.data ?? []).map((c, i) => (
          <Stack key={i} gap={6}>
            <Group gap="xs">
              <Text size="sm" fw={600}>
                {t("assistant.sent.step", { n: i + 1 })}
              </Text>
              <Badge size="sm" color={c.location === "cloud" ? "orange" : "teal"} variant="light">
                {t(`assistant.location.${c.location}`)}
              </Badge>
              <Badge size="sm" variant="outline" color="gray">
                {c.profile_name} · {c.model}
              </Badge>
              {c.modules.map((m) => (
                <Badge key={m} size="sm" variant="light" color="grape">
                  {t(`assistant.module.${m}`)}
                </Badge>
              ))}
              {c.images > 0 && (
                <Badge size="sm" variant="light" color="red">
                  {t("assistant.sent.images", { count: c.images })}
                </Badge>
              )}
              <Text size="xs" c="dimmed">
                {fmtDateTime(c.created_at)}
                {c.input_tokens != null && ` · ${c.input_tokens} / ${c.output_tokens ?? 0} tok.`}
              </Text>
            </Group>
            {!c.ok && (
              <Text size="sm" c="red">
                {c.error}
              </Text>
            )}
            <ScrollArea.Autosize mah={300}>
              <Stack gap={4}>
                {c.sent.map((m, j) => (
                  <Code key={j} block style={{ whiteSpace: "pre-wrap" }}>
                    {`${m.role}: ${m.text}`}
                  </Code>
                ))}
              </Stack>
            </ScrollArea.Autosize>
          </Stack>
        ))}
      </Stack>
    </Modal>
  );
}
