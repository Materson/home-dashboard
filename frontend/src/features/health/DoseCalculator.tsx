/**
 * Weight-based dose for one cabinet medicine. The server does the maths
 * (apps/health/dosing.py — same numbers the assistant will use); this picks
 * a person (pre-filling their latest weight and checking their age) or takes
 * a typed weight, and shows the result with every warning.
 */
import { useEffect, useState } from "react";
import { Alert, Button, Group, Paper, Select, Stack, Text, Title } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { AmountInput, isPositiveAmount } from "@/components/AmountInput";
import { fmtNumber } from "@/lib/format";

import { cabinetApi, healthApi, type CabinetItem } from "./api";

/** 1.25 → "1¼" */
function units(value: string): string {
  const n = Number(value);
  const whole = Math.floor(n);
  const frac = { 0: "", 0.25: "¼", 0.5: "½", 0.75: "¾" }[n - whole] ?? "";
  return `${whole || (frac ? "" : "0")}${frac}`;
}

export function DoseCalculator({
  item,
  initialPersonId = null,
  onUse,
}: {
  item: CabinetItem;
  initialPersonId?: string | null;
  /** Show "use this dose" and hand over the dose text (e.g. "5,0 ml"). */
  onUse?: (dosage: string) => void;
}) {
  const { t } = useTranslation();
  const [personId, setPersonId] = useState<string | null>(initialPersonId);
  const [weight, setWeight] = useState("");
  const [debouncedWeight] = useDebouncedValue(weight, 300);

  const people = useQuery({ queryKey: ["health", "people"], queryFn: () => healthApi.people() });
  const measurements = useQuery({
    queryKey: ["health", personId, "measurements"],
    queryFn: () => healthApi.list("measurements", { person_id: personId! }),
    enabled: !!personId,
  });
  // Picking a person pre-fills their most recent recorded weight.
  useEffect(() => {
    const latest = measurements.data?.find((m) => m.weight_kg);
    if (latest) setWeight(String(latest.weight_kg));
  }, [measurements.data]);

  const ready = isPositiveAmount(debouncedWeight);
  const dose = useQuery({
    queryKey: ["cabinet", "dose", item.id, debouncedWeight, personId],
    queryFn: () => cabinetApi.dose(item.id, debouncedWeight, personId),
    enabled: ready,
  });
  const r = dose.data;
  const perMl = item.strength_volume_ml != null;
  // The single dose as one would write it on the treatment.
  const doseText = !r
    ? ""
    : r.single_ml != null && (perMl || !r.single_mg)
      ? `${fmtNumber(r.single_ml, 1)} ml`
      : r.single_units != null && Number(r.single_units) > 0
        ? t("cabinet.calc.units", { units: units(r.single_units) })
        : r.single_mg
          ? `${fmtNumber(r.single_mg, 1)} mg`
          : "";

  return (
    <Paper withBorder p="sm">
      <Stack gap="sm">
        <Title order={6}>{t("cabinet.calc.title")}</Title>
        <Group grow align="flex-start">
          <Select
            label={t("cabinet.calc.person")}
            placeholder={t("cabinet.calc.anyone")}
            clearable
            data={(people.data ?? []).map((p) => ({ value: p.id, label: p.display_name }))}
            value={personId}
            onChange={setPersonId}
          />
          <AmountInput label={t("cabinet.calc.weight")} value={weight} onChange={setWeight} />
        </Group>
        {personId && measurements.isSuccess && !measurements.data.some((m) => m.weight_kg) && (
          <Text size="xs" c="dimmed">
            {t("cabinet.calc.noWeight")}
          </Text>
        )}

        {ready && r && (
          <Stack gap={4}>
            {r.single_ml != null && (perMl || !r.single_mg) && (
              <Text size="xl" fw={700}>
                {fmtNumber(r.single_ml, 1)} ml
                {r.single_mg && (
                  <Text span size="sm" c="dimmed" fw={400}>
                    {" "}
                    ({fmtNumber(r.single_mg, 1)} mg)
                  </Text>
                )}
              </Text>
            )}
            {r.single_units != null && Number(r.single_units) > 0 && (
              <Text size="xl" fw={700}>
                {t("cabinet.calc.units", { units: units(r.single_units) })}
                <Text span size="sm" c="dimmed" fw={400}>
                  {" "}
                  ({fmtNumber(r.single_mg, 1)} mg)
                </Text>
              </Text>
            )}
            {r.single_mg && r.single_ml == null && r.single_units == null && (
              // mg/kg rule without a strength on file: only the mg are known
              <Text size="xl" fw={700}>
                {fmtNumber(r.single_mg, 1)} mg
              </Text>
            )}
            {r.daily_max_mg && (
              <Text size="sm">
                {t("cabinet.calc.dailyMax", {
                  amount: r.daily_max_ml
                    ? `${fmtNumber(r.daily_max_ml, 1)} ml (${fmtNumber(r.daily_max_mg, 1)} mg)`
                    : `${fmtNumber(r.daily_max_mg, 1)} mg`,
                })}
                {r.max_doses_per_day != null && ` · ${t("cabinet.calc.dosesPerDay", { count: r.max_doses_per_day })}`}
              </Text>
            )}
            {r.min_interval_hours && (
              <Text size="sm">{t("cabinet.calc.interval", { hours: r.min_interval_hours })}</Text>
            )}
            {onUse && doseText && (
              <Button
                size="xs"
                variant="light"
                style={{ alignSelf: "flex-start" }}
                onClick={() => onUse(doseText)}
              >
                {t("cabinet.calc.use", { dose: doseText })}
              </Button>
            )}
            {r.warnings.map((w) => (
              <Alert
                key={w}
                color={w === "too_young" || w === "below_quarter_unit" ? "red" : "orange"}
                icon={<IconAlertTriangle size={16} />}
                p="xs"
              >
                {t(`cabinet.calc.warn.${w}`)}
              </Alert>
            ))}
          </Stack>
        )}
        <Text size="xs" c="dimmed">
          {t("cabinet.calc.disclaimer")}
        </Text>
      </Stack>
    </Paper>
  );
}
