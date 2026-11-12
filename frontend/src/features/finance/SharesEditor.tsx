/**
 * "Dla kogo": pick the people a transaction was for. With several people
 * the amount is split equally (and re-split when the amount or the people
 * change) until you edit a part yourself; "Po równo" splits again. Nobody
 * picked = the household's.
 */
import { useEffect, useState } from "react";
import { Button, Group, MultiSelect, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { AmountInput } from "@/components/AmountInput";
import { peopleApi } from "@/features/people/api";
import { fmtMoney } from "@/lib/format";

import { equalSplit, remainder, type Share, sharesValid } from "./shares";

export function SharesEditor(props: {
  amount: string;
  currency: string;
  value: Share[];
  onChange: (shares: Share[]) => void;
}) {
  const { t } = useTranslation();
  const people = useQuery({ queryKey: ["people"], queryFn: () => peopleApi.list() });
  const names = Object.fromEntries((people.data ?? []).map((p) => [p.id, p.display_name]));
  const ids = props.value.map((s) => s.person_id);
  // Edited by hand → stop re-splitting automatically.
  const [manual, setManual] = useState(() => {
    const even = equalSplit(props.amount, ids);
    return props.value.some((s, i) => s.amount !== even[i]?.amount);
  });

  useEffect(() => {
    if (manual || !ids.length) return;
    const even = equalSplit(props.amount, ids);
    if (even.some((s, i) => s.amount !== props.value[i]?.amount)) props.onChange(even);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-split on amount / people only
  }, [props.amount, ids.join(","), manual]);

  const pick = (next: string[]) => {
    setManual(false);
    props.onChange(equalSplit(props.amount, next));
  };
  const setPart = (personId: string, amount: string) => {
    setManual(true);
    props.onChange(props.value.map((s) => (s.person_id === personId ? { ...s, amount } : s)));
  };
  const left = remainder(props.amount, props.value);

  return (
    <Stack gap={6}>
      <MultiSelect
        label={t("finance.field.forWhom")}
        placeholder={ids.length ? undefined : t("finance.field.forWhomShared")}
        data={(people.data ?? []).map((p) => ({ value: p.id, label: p.display_name }))}
        value={ids}
        onChange={pick}
        clearable
        searchable
      />
      {props.value.length > 1 && (
        <Stack gap={4} pl="sm">
          {props.value.map((s) => (
            <Group key={s.person_id} gap="xs" wrap="nowrap">
              <Text size="sm" w={120} truncate>
                {names[s.person_id] ?? "…"}
              </Text>
              <AmountInput size="xs" value={s.amount} onChange={(v) => setPart(s.person_id, v)} style={{ flex: 1 }} />
            </Group>
          ))}
          <Group justify="space-between">
            <Text size="xs" c={sharesValid(props.amount, props.value) ? "dimmed" : "red"}>
              {Number(left) === 0
                ? t("finance.split.ok")
                : t("finance.split.left", { amount: fmtMoney(left, props.currency) })}
            </Text>
            {manual && (
              <Button size="compact-xs" variant="subtle" onClick={() => pick(ids)}>
                {t("finance.split.equal")}
              </Button>
            )}
          </Group>
        </Stack>
      )}
    </Stack>
  );
}
