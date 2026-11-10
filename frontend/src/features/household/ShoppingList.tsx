/**
 * The shared shopping list. Items below their minimum appear by themselves
 * (marked "kończy się"); anyone can add free text. Ticking a line that is a
 * known item asks how much was bought (and until when it's good) and adds
 * it to the stock — or just ticks it. Ticked lines stay at the bottom for a
 * while so a mis-tap can be undone.
 */
import { useState } from "react";
import {
  ActionIcon,
  Autocomplete,
  Badge,
  Button,
  Checkbox,
  Group,
  Modal,
  Paper,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { DatePickerInput } from "@mantine/dates";
import { IconPlus, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { AmountInput, isPositiveAmount } from "@/components/AmountInput";
import { isoDate, parseIsoDate } from "@/lib/format";

import { HOUSEHOLD_KEY, householdApi, type ShoppingEntry } from "./api";

/** "2 opak." → "2"; "1,5 l" → "1.5"; "" → "1". */
export function boughtGuess(quantity: string): string {
  const m = quantity.match(/\d+(?:[.,]\d+)?/);
  return m ? m[0].replace(",", ".") : "1";
}

export function ShoppingList({ canEdit, itemNames }: { canEdit: boolean; itemNames: string[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState("");
  const [ticking, setTicking] = useState<ShoppingEntry | null>(null);

  const list = useQuery({ queryKey: [...HOUSEHOLD_KEY, "shopping"], queryFn: householdApi.shopping });
  const refresh = () => qc.invalidateQueries({ queryKey: HOUSEHOLD_KEY });
  const add = useMutation({
    mutationFn: () => householdApi.addEntry({ name, quantity }),
    onSuccess: () => {
      setName("");
      setQuantity("");
      refresh();
    },
  });
  const tick = useMutation({
    mutationFn: (v: { id: string; bought?: string; expiry_date?: string | null }) =>
      householdApi.tick(v.id, { bought: v.bought, expiry_date: v.expiry_date }),
    onSuccess: () => {
      setTicking(null);
      refresh();
    },
  });
  const untick = useMutation({ mutationFn: householdApi.untick, onSuccess: refresh });
  const remove = useMutation({ mutationFn: householdApi.deleteEntry, onSuccess: refresh });
  const clearDone = useMutation({ mutationFn: householdApi.clearDone, onSuccess: refresh });

  const entries = list.data ?? [];
  const todo = entries.filter((e) => !e.done_at);
  const done = entries.filter((e) => e.done_at);

  const onCheck = (e: ShoppingEntry) => {
    if (e.done_at) untick.mutate(e.id);
    else if (e.item_id) setTicking(e); // ask how much went into stock
    else tick.mutate({ id: e.id });
  };

  return (
    <Stack gap="sm">
      {canEdit && (
        <form
          onSubmit={(ev) => {
            ev.preventDefault();
            if (name.trim()) add.mutate();
          }}
        >
          <Group align="flex-end" wrap="nowrap" gap="xs">
            <Autocomplete
              style={{ flex: 1 }}
              placeholder={t("household.shopping.addPlaceholder")}
              data={itemNames}
              limit={8}
              value={name}
              onChange={setName}
            />
            <TextInput
              w={110}
              placeholder={t("household.shopping.qtyPlaceholder")}
              value={quantity}
              onChange={(ev) => setQuantity(ev.currentTarget.value)}
            />
            <ActionIcon type="submit" size="lg" disabled={!name.trim()} loading={add.isPending}>
              <IconPlus size={18} />
            </ActionIcon>
          </Group>
        </form>
      )}

      <Paper withBorder>
        {todo.length === 0 && list.isSuccess && (
          <Text c="dimmed" ta="center" py="lg" size="sm">
            {t("household.shopping.empty")}
          </Text>
        )}
        {[...todo, ...done].map((e) => (
          <Group key={e.id} px="md" py="xs" wrap="nowrap" justify="space-between" style={{ borderBottom: "1px solid var(--mantine-color-default-border)" }}>
            <Checkbox
              size="md"
              checked={!!e.done_at}
              disabled={!canEdit}
              onChange={() => onCheck(e)}
              label={
                <Group gap={6} wrap="nowrap">
                  <Text td={e.done_at ? "line-through" : undefined} c={e.done_at ? "dimmed" : undefined}>
                    {e.name}
                  </Text>
                  {e.quantity && (
                    <Text size="sm" c="dimmed">
                      {e.quantity}
                    </Text>
                  )}
                  {e.auto && !e.done_at && (
                    <Badge size="xs" color="orange" variant="light">
                      {t("household.shopping.runningLow")}
                    </Badge>
                  )}
                </Group>
              }
            />
            {canEdit && (
              <ActionIcon variant="subtle" color="gray" aria-label={t("finance.action.delete")} onClick={() => remove.mutate(e.id)}>
                <IconTrash size={16} />
              </ActionIcon>
            )}
          </Group>
        ))}
      </Paper>

      {canEdit && done.length > 0 && (
        <Group justify="flex-end">
          <Button size="xs" variant="subtle" color="gray" onClick={() => clearDone.mutate()}>
            {t("household.shopping.clearDone", { count: done.length })}
          </Button>
        </Group>
      )}

      <TickModal
        entry={ticking}
        onClose={() => setTicking(null)}
        onTick={(bought, expiry) => ticking && tick.mutate({ id: ticking.id, bought, expiry_date: expiry })}
        pending={tick.isPending}
      />
    </Stack>
  );
}

function TickModal(props: {
  entry: ShoppingEntry | null;
  onClose: () => void;
  onTick: (bought?: string, expiry?: string | null) => void;
  pending: boolean;
}) {
  const e = props.entry;
  return (
    <Modal opened={!!e} onClose={props.onClose} title={e?.name ?? ""}>
      {/* Remount per line so the guess is fresh each time. */}
      {e && <TickForm key={e.id} entry={e} onTick={props.onTick} pending={props.pending} />}
    </Modal>
  );
}

function TickForm(props: {
  entry: ShoppingEntry;
  onTick: (bought?: string, expiry?: string | null) => void;
  pending: boolean;
}) {
  const { t } = useTranslation();
  const [bought, setBought] = useState(boughtGuess(props.entry.quantity));
  const [expiry, setExpiry] = useState<string | null>(null);
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        {t("household.shopping.tickHint")}
      </Text>
      <Group grow align="flex-start">
        <AmountInput
          label={t("household.shopping.bought", { unit: props.entry.unit ?? "" })}
          value={bought}
          onChange={setBought}
        />
        <DatePickerInput
          label={t("household.f.expiry")}
          clearable
          value={expiry ? parseIsoDate(expiry) : null}
          onChange={(d) => setExpiry(d ? isoDate(d) : null)}
        />
      </Group>
      <Group justify="space-between">
        <Button variant="subtle" color="gray" onClick={() => props.onTick()} loading={props.pending}>
          {t("household.shopping.justTick")}
        </Button>
        <Button
          disabled={!isPositiveAmount(bought)}
          loading={props.pending}
          onClick={() => props.onTick(bought, expiry)}
        >
          {t("household.shopping.addToStock")}
        </Button>
      </Group>
    </Stack>
  );
}
