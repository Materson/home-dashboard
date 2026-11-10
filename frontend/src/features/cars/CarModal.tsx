import { useEffect, useState } from "react";
import { Button, Group, Modal, NumberInput, Select, Stack, Textarea, TextInput } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { carsApi, type Car, type CarInput, type FuelType } from "./api";

const FUEL_TYPES: FuelType[] = ["petrol", "diesel", "lpg", "hybrid", "electric"];

const EMPTY: CarInput = {
  name: "",
  make: "",
  model: "",
  year: null,
  plate: "",
  vin: "",
  fuel_type: "petrol",
  owner_id: null,
  initial_odometer_km: 0,
  oil_interval_km: 15000,
  oil_interval_months: 12,
  notes: "",
};

export function CarModal(props: {
  opened: boolean;
  car: Car | null;
  onClose: () => void;
  onSaved: (car: Car) => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [form, setForm] = useState<CarInput>(EMPTY);
  const people = useQuery({ queryKey: ["people"], queryFn: () => carsApi.listPeople() });

  useEffect(() => {
    if (!props.opened) return;
    if (props.car) {
      const { id: _id, archived: _archived, ...input } = props.car;
      setForm(input);
    } else {
      setForm(EMPTY);
    }
  }, [props.opened, props.car]);

  const save = useMutation({
    mutationFn: () => (props.car ? carsApi.update(props.car.id, form) : carsApi.create(form)),
    onSuccess: (car) => {
      qc.invalidateQueries({ queryKey: ["cars"] });
      props.onSaved(car);
      props.onClose();
    },
  });

  const int = (v: string | number) => (v === "" ? 0 : Number(v));

  return (
    <Modal
      opened={props.opened}
      onClose={props.onClose}
      title={t(props.car ? "cars.editCar" : "cars.addCar")}
    >
      <Stack>
        <TextInput
          label={t("cars.car.name")}
          description={t("cars.car.nameHint")}
          required
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
          data-autofocus
        />
        <Group grow>
          <TextInput
            label={t("cars.car.make")}
            value={form.make}
            onChange={(e) => setForm({ ...form, make: e.currentTarget.value })}
          />
          <TextInput
            label={t("cars.car.model")}
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.currentTarget.value })}
          />
        </Group>
        <Group grow>
          <NumberInput
            label={t("cars.car.year")}
            hideControls
            allowDecimal={false}
            value={form.year ?? ""}
            onChange={(v) => setForm({ ...form, year: v === "" ? null : Number(v) })}
          />
          <TextInput
            label={t("cars.car.plate")}
            value={form.plate}
            onChange={(e) => setForm({ ...form, plate: e.currentTarget.value.toUpperCase() })}
          />
        </Group>
        <TextInput
          label={t("cars.car.vin")}
          maxLength={17}
          value={form.vin}
          onChange={(e) => setForm({ ...form, vin: e.currentTarget.value.toUpperCase() })}
        />
        <Group grow>
          <Select
            label={t("cars.car.fuelType")}
            allowDeselect={false}
            data={FUEL_TYPES.map((f) => ({ value: f, label: t(`cars.fuelType.${f}`) }))}
            value={form.fuel_type}
            onChange={(v) => setForm({ ...form, fuel_type: (v as FuelType) ?? "petrol" })}
          />
          <Select
            label={t("cars.car.owner")}
            clearable
            data={(people.data ?? []).map((p) => ({ value: p.id, label: p.display_name }))}
            value={form.owner_id}
            onChange={(v) => setForm({ ...form, owner_id: v })}
          />
        </Group>
        <NumberInput
          label={t("cars.car.initialOdometer")}
          description={t("cars.car.initialOdometerHint")}
          hideControls
          allowDecimal={false}
          allowNegative={false}
          thousandSeparator=" "
          value={form.initial_odometer_km}
          onChange={(v) => setForm({ ...form, initial_odometer_km: int(v) })}
        />
        <Group grow>
          <NumberInput
            label={t("cars.car.oilIntervalKm")}
            hideControls
            allowDecimal={false}
            allowNegative={false}
            thousandSeparator=" "
            value={form.oil_interval_km}
            onChange={(v) => setForm({ ...form, oil_interval_km: int(v) })}
          />
          <NumberInput
            label={t("cars.car.oilIntervalMonths")}
            hideControls
            allowDecimal={false}
            allowNegative={false}
            value={form.oil_interval_months}
            onChange={(v) => setForm({ ...form, oil_interval_months: int(v) })}
          />
        </Group>
        <Textarea
          label={t("cars.f.notes")}
          autosize
          minRows={2}
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.currentTarget.value })}
        />
        <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!form.name.trim()}>
          {t("finance.action.save")}
        </Button>
      </Stack>
    </Modal>
  );
}
