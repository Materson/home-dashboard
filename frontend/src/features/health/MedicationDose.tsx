/**
 * The dose calculator inside the treatment form, under Dosage. "Oblicz dawkę"
 * opens the calculator for the form's person; its result can be put into the
 * Dosage field. If the medicine has no weight-based rule yet — or isn't in
 * the cabinet at all — its cabinet form opens on top (pre-filled with the
 * typed name) so the rule can be added without leaving the treatment; the
 * calculator then appears in place. Saving the treatment links it to that
 * cabinet item by name.
 */
import { useState } from "react";
import { Alert, Button, Collapse, Stack, Text } from "@mantine/core";
import { IconCalculator, IconPencil, IconPlus } from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { Row } from "@/components/records/fields";
import { type FormExtra, RecordFormModal } from "@/components/records/RecordFormModal";

import { cabinetApi, type CabinetItem } from "./api";
import { DoseCalculator } from "./DoseCalculator";
import { CABINET_ITEM_FIELDS } from "./fields";

export function hasDoseRule(item: CabinetItem): boolean {
  return item.dose_mg_per_kg != null || item.dose_ml_per_kg != null;
}

/** Form extra for the medications form, given the cabinet's medicines. */
export function medicationDoseExtra(cabinet: CabinetItem[]): FormExtra {
  return function MedicationDoseExtra(state, set) {
    const name = String(state.name ?? "").trim();
    if (!name) return null;
    const item = cabinet.find((i) => i.name.toLowerCase() === name.toLowerCase());
    const personId = state.person_id ? String(state.person_id) : null;
    return (
      // Keyed by person only, so the panel stays open when the medicine is
      // added to the cabinet (or gets its rule) from here.
      <MedicationDose
        key={personId ?? ""}
        name={name}
        item={item}
        personId={personId}
        onUse={(dosage) => set("dosage", dosage)}
        onNamed={(saved) => set("name", saved)}
      />
    );
  };
}

function MedicationDose(props: {
  name: string;
  item: CabinetItem | undefined;
  personId: string | null;
  onUse: (dosage: string) => void;
  /** The cabinet item was saved under this name — the treatment follows it. */
  onNamed: (name: string) => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const { item } = props;

  let body;
  if (item && hasDoseRule(item)) {
    body = (
      <DoseCalculator key={item.id} item={item} initialPersonId={props.personId} onUse={props.onUse} />
    );
  } else {
    body = (
      <Alert color="gray" p="sm">
        <Stack gap="xs">
          <Text size="sm">
            {item
              ? t("cabinet.calc.noRuleYet", { name: item.name })
              : t("cabinet.calc.notInCabinet", { name: props.name })}
          </Text>
          <Button
            size="xs"
            variant="light"
            leftSection={item ? <IconPencil size={14} /> : <IconPlus size={14} />}
            style={{ alignSelf: "flex-start" }}
            onClick={() => setEditing(true)}
          >
            {t(item ? "cabinet.calc.addRule" : "cabinet.calc.addToCabinet")}
          </Button>
        </Stack>
      </Alert>
    );
  }

  return (
    <Stack gap="xs">
      <Button
        variant="light"
        size="xs"
        leftSection={<IconCalculator size={14} />}
        onClick={() => setOpen((o) => !o)}
        style={{ alignSelf: "flex-start" }}
      >
        {t("cabinet.calc.open")}
      </Button>
      <Collapse in={open}>{open && body}</Collapse>
      <RecordFormModal
        fields={CABINET_ITEM_FIELDS}
        record={editing && item ? (item as unknown as Row) : null}
        defaults={{ name: props.name }}
        opened={editing}
        onClose={() => setEditing(false)}
        onSave={(payload) =>
          cabinetApi.saveItem(payload, item?.id).then((saved) => {
            props.onNamed(saved.name);
            return saved;
          })
        }
        onSaved={() => qc.invalidateQueries({ queryKey: ["cabinet"] })}
        titleKey={{ add: "cabinet.addMedicine", edit: "cabinet.editMedicine" }}
      />
    </Stack>
  );
}
