/**
 * Car records: the shared field-driven list/form (components/records) wired
 * to the cars API. Any change refreshes the whole car (odometer, costs and
 * reminders depend on every record) and Finance (costs land in the ledger).
 */
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { RecordFormModal } from "@/components/records/RecordFormModal";
import { RecordList } from "@/components/records/RecordList";
import { fmtNumber } from "@/lib/format";

import { carsApi, type CarRecord, type RecordKind } from "./api";
import { RECORDS } from "./records";

const LABELS = {
  add: "cars.addRecord",
  edit: "cars.editRecord",
  empty: "cars.noRecords",
  deleteConfirm: "cars.deleteConfirm",
};

export function RecordSection({ carId, kind }: { carId: string; kind: RecordKind }) {
  const { t } = useTranslation();
  return (
    <RecordList
      fields={RECORDS[kind]}
      queryKey={["cars", carId, kind]}
      list={() => carsApi.records(carId, kind)}
      save={(payload, id) => carsApi.saveRecord(carId, kind, payload, id)}
      remove={(id) => carsApi.deleteRecord(carId, kind, id)}
      invalidate={[["cars", carId], ["finance"]]}
      labels={LABELS}
      extraColumns={
        kind === "fuel"
          ? [
              {
                headerKey: "cars.f.effectivePrice",
                numeric: true,
                render: (r) => fmtNumber(r.effective_price_per_litre as string, 2),
                // Phones: only when a discount made it differ from the pump price.
                phoneText: (r) =>
                  r.discount ? t("cars.phone.effective", { value: fmtNumber(r.effective_price_per_litre as string, 2) }) : null,
              },
            ]
          : undefined
      }
    />
  );
}

/** The car record form on its own (used by the Service and Odometer tabs). */
export function RecordModal(props: {
  carId: string;
  kind: RecordKind;
  record: CarRecord | null;
  opened: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  return (
    <RecordFormModal
      fields={RECORDS[props.kind]}
      record={props.record}
      opened={props.opened}
      onClose={props.onClose}
      onSave={(payload) =>
        carsApi.saveRecord(props.carId, props.kind, payload, props.record?.id)
      }
      onSaved={() => {
        qc.invalidateQueries({ queryKey: ["cars", props.carId] });
        qc.invalidateQueries({ queryKey: ["finance"] });
      }}
      titleKey={{ add: LABELS.add, edit: LABELS.edit }}
    />
  );
}
