/**
 * A person's health at a glance: age, weight, height, BMI (adult bands only —
 * children are judged on percentile charts), weight/height trend, current
 * treatments and upcoming visits. Used on the health page and People profile.
 */
import { useState } from "react";
import { Badge, Button, Group, Paper, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { LineChart } from "@mantine/charts";
import { IconRuler } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { RecordFormModal } from "@/components/records/RecordFormModal";
import { usePermissions } from "@/features/auth/usePermissions";
import { fmtDate, fmtDateTime, fmtNumber } from "@/lib/format";

import { healthApi } from "./api";
import { HEALTH_RECORDS } from "./fields";
import { HEALTH_INVALIDATE, useHealthForms } from "./useHealthForms";

const BMI_COLOR = { underweight: "orange", normal: "teal", overweight: "orange", obese: "red" } as const;

export function ageText(months: number | null, t: (k: string, o?: Record<string, unknown>) => string) {
  if (months == null) return "—";
  return months < 24 ? t("health.profile.ageMonths", { count: months }) : t("health.profile.ageYears", { count: Math.floor(months / 12) });
}

export function ProfileSummary({ personId }: { personId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const canEdit = usePermissions().canEdit("health");
  const forms = useHealthForms(personId);
  const [measuring, setMeasuring] = useState(false);
  const q = useQuery({
    queryKey: ["health", personId, "profile"],
    queryFn: () => healthApi.profile(personId),
  });
  const p = q.data;
  if (!p) return null; // loading, or no health access to this person

  const chart = p.measurements
    .filter((m) => m.weight_kg || m.height_cm)
    .map((m) => ({
      date: fmtDate(String(m.date)),
      weight: m.weight_kg ? Number(m.weight_kg) : null,
      height: m.height_cm ? Number(m.height_cm) : null,
    }));

  return (
    <Stack gap="sm">
      {canEdit && (
        <Group justify="flex-end">
          <Button size="xs" variant="light" leftSection={<IconRuler size={14} />} onClick={() => setMeasuring(true)}>
            {t("health.profile.addMeasurement")}
          </Button>
        </Group>
      )}
      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        <Tile label={t("health.profile.age")} value={ageText(p.age_months, t)} />
        <Tile
          label={t("health.f.weight")}
          value={p.weight_kg ? `${fmtNumber(p.weight_kg, 1)} kg` : "—"}
          sub={p.weight_date ? fmtDate(p.weight_date) : t("health.profile.noData")}
        />
        <Tile
          label={t("health.f.height")}
          value={p.height_cm ? `${fmtNumber(p.height_cm, 0)} cm` : "—"}
          sub={p.height_date ? fmtDate(p.height_date) : t("health.profile.noData")}
        />
        <Paper withBorder p="md">
          <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
            BMI
          </Text>
          <Group gap="xs">
            <Text size="xl" fw={700}>
              {p.bmi ? fmtNumber(p.bmi, 1) : "—"}
            </Text>
            {p.bmi_category && p.bmi_category !== "child" && (
              <Badge color={BMI_COLOR[p.bmi_category]} variant="light">
                {t(`health.profile.bmi.${p.bmi_category}`)}
              </Badge>
            )}
          </Group>
          {p.bmi_category === "child" && (
            <Text size="xs" c="dimmed">
              {t("health.profile.bmiChild")}
            </Text>
          )}
        </Paper>
      </SimpleGrid>

      {chart.length > 1 && (
        <Paper withBorder p="md">
          <Title order={6} mb="xs">
            {t("health.profile.trend")}
          </Title>
          <LineChart
            h={180}
            data={chart}
            dataKey="date"
            withRightYAxis
            connectNulls
            series={[
              { name: "weight", label: t("health.f.weight"), color: "indigo.6" },
              { name: "height", label: t("health.f.height"), color: "teal.6", yAxisId: "right" },
            ]}
          />
        </Paper>
      )}

      {(p.treatments.length > 0 || p.upcoming_visits.length > 0) && (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          <Paper withBorder p="md">
            <Title order={6} mb="xs">
              {t("health.profile.currentTreatments")}
            </Title>
            {p.treatments.length ? (
              p.treatments.map((m) => (
                <Text key={m.id} size="sm">
                  <b>{String(m.name)}</b>
                  {m.dosage ? ` · ${String(m.dosage)}` : ""}
                  {Array.isArray(m.dose_times) && m.dose_times.length ? ` · ${m.dose_times.join(", ")}` : ""}
                </Text>
              ))
            ) : (
              <Text size="sm" c="dimmed">
                {t("health.profile.none")}
              </Text>
            )}
          </Paper>
          <Paper withBorder p="md">
            <Title order={6} mb="xs">
              {t("health.profile.upcomingVisits")}
            </Title>
            {p.upcoming_visits.length ? (
              p.upcoming_visits.map((v) => (
                <Text key={v.id} size="sm">
                  <b>{fmtDateTime(String(v.starts_at))}</b>
                  {[v.specialty, v.doctor, v.place, v.room].filter(Boolean).map(String).join(" · ")
                    ? ` · ${[v.specialty, v.doctor, v.place, v.room].filter(Boolean).map(String).join(" · ")}`
                    : ""}
                </Text>
              ))
            ) : (
              <Text size="sm" c="dimmed">
                {t("health.profile.none")}
              </Text>
            )}
          </Paper>
        </SimpleGrid>
      )}

      <RecordFormModal
        fields={HEALTH_RECORDS.measurements}
        record={null}
        opened={measuring}
        onClose={() => setMeasuring(false)}
        onSave={(payload) => healthApi.save("measurements", payload)}
        onSaved={() => {
          for (const key of HEALTH_INVALIDATE) qc.invalidateQueries({ queryKey: key });
        }}
        titleKey={{ add: "health.profile.addMeasurement", edit: "health.edit" }}
        choices={forms.choices}
        // Start from the latest values: usually only one of them changed.
        defaults={{
          person_id: personId,
          weight_kg: p.weight_kg ? String(p.weight_kg) : "",
          height_cm: p.height_cm ? String(p.height_cm) : "",
        }}
      />
    </Stack>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Paper withBorder p="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="xl" fw={700}>
        {value}
      </Text>
      {sub && (
        <Text size="xs" c="dimmed">
          {sub}
        </Text>
      )}
    </Paper>
  );
}
