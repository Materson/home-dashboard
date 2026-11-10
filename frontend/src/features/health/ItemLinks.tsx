/**
 * In a cabinet medicine's panel: who takes / took it (treatments, any
 * person in your health scope) and what was paid for it (Finance
 * transactions linked to it — only shown with finance access).
 */
import { Anchor, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { usePermissions } from "@/features/auth/usePermissions";
import { fmtDate, fmtMoney } from "@/lib/format";

import { cabinetApi, healthApi } from "./api";

export function ItemLinks({ itemId }: { itemId: string }) {
  const { t } = useTranslation();
  const canSeeFinance = usePermissions().canView("finance");
  const treatments = useQuery({
    queryKey: ["health", "treatments-of", itemId],
    queryFn: () => healthApi.list("medications", { cabinet_item_id: itemId }),
  });
  const purchases = useQuery({
    queryKey: ["cabinet", "purchases", itemId],
    queryFn: () => cabinetApi.purchases(itemId),
    enabled: canSeeFinance,
  });

  return (
    <Stack gap="sm" mt="md">
      <Title order={5}>{t("cabinet.links.treatments")}</Title>
      {treatments.isSuccess && !treatments.data.length && (
        <Text size="sm" c="dimmed">
          {t("cabinet.links.noTreatments")}
        </Text>
      )}
      {(treatments.data ?? []).map((m) => (
        <Text key={m.id} size="sm">
          <Anchor component={Link} to={`/health/${String(m.person_id)}`}>
            {String(m.person_name)}
          </Anchor>
          {" · "}
          {fmtDate(String(m.start_date))} – {m.end_date ? fmtDate(String(m.end_date)) : t("health.event.ongoing")}
          {m.dosage ? ` · ${String(m.dosage)}` : ""}
        </Text>
      ))}

      {canSeeFinance && (
        <>
          <Title order={5}>{t("cabinet.links.purchases")}</Title>
          {purchases.isSuccess && !purchases.data.length && (
            <Text size="sm" c="dimmed">
              {t("cabinet.links.noPurchases")}
            </Text>
          )}
          {(purchases.data ?? []).map((p) => (
            <Text key={p.id} size="sm">
              {fmtDate(p.date)} · {p.name} · <b>{fmtMoney(p.amount, p.currency)}</b>
            </Text>
          ))}
        </>
      )}
    </Stack>
  );
}
