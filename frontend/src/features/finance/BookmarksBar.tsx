/**
 * A strip of the user's saved transaction templates. Clicking one opens the
 * add-transaction form pre-filled (today's date) so the amount can still be
 * adjusted before saving; the × removes the bookmark.
 */
import { ActionIcon, Button, Group, Text, Tooltip } from "@mantine/core";
import { IconBookmark, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { financeApi, type Bookmark } from "./api";

export function BookmarksBar({ onPick }: { onPick: (bookmark: Bookmark) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const bookmarks = useQuery({
    queryKey: ["finance", "bookmarks"],
    queryFn: () => financeApi.listBookmarks(),
  });
  const remove = useMutation({
    mutationFn: (id: string) => financeApi.deleteBookmark(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["finance", "bookmarks"] }),
  });

  const items = bookmarks.data ?? [];
  return (
    <Group gap="xs" wrap="wrap">
      <IconBookmark size={18} />
      {!items.length && (
        <Text size="sm" c="dimmed">
          {t("finance.bookmarks.empty")}
        </Text>
      )}
      {items.map((b) => (
        <Button.Group key={b.id}>
          <Tooltip label={`${b.name} · ${b.amount} ${b.currency}`}>
            <Button variant="light" size="xs" onClick={() => onPick(b)}>
              {b.label}
            </Button>
          </Tooltip>
          <ActionIcon
            variant="light"
            size={30}
            color="gray"
            aria-label={t("finance.bookmarks.remove")}
            onClick={() => remove.mutate(b.id)}
          >
            <IconX size={12} />
          </ActionIcon>
        </Button.Group>
      ))}
    </Group>
  );
}
