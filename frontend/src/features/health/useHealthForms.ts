/**
 * Everything the health forms need to offer choices, for one person:
 * who (health-scoped people), which illness/event, medicine names from the
 * cabinet, and values from earlier visits (a picked doctor fills their
 * usual specialty / place / room).
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import type { Choices, Fills, Row, Suggestions } from "@/components/records/fields";

import { cabinetApi, healthApi } from "./api";

export function useHealthForms(personId: string) {
  const people = useQuery({ queryKey: ["health", "people"], queryFn: () => healthApi.people() });
  const conditions = useQuery({
    queryKey: ["health", personId, "conditions"],
    queryFn: () => healthApi.list("conditions", { person_id: personId }),
  });
  // Every event the user may see (not just this person's): "Angina" typed for
  // one child is offered for the next.
  const allEvents = useQuery({
    queryKey: ["health", "all", "conditions"],
    queryFn: () => healthApi.list("conditions", {}),
  });
  const symptoms = useQuery({
    queryKey: ["health", personId, "symptoms"],
    queryFn: () => healthApi.list("symptoms", { person_id: personId }),
  });
  const cabinet = useQuery({
    queryKey: ["cabinet", "", "all", false],
    queryFn: () => cabinetApi.list("", "all", false),
  });
  const visits = useQuery({
    queryKey: ["health", "appointment-suggestions"],
    queryFn: () => healthApi.appointmentSuggestions(),
  });

  return useMemo(() => {
    const choices: Choices = {
      person_id: (people.data ?? []).map((p) => ({ value: p.id, label: p.display_name })),
      condition_id: (conditions.data ?? []).map((c) => ({ value: c.id, label: String(c.title) })),
    };
    const v = visits.data;
    const suggestions: Suggestions = {
      name: (cabinet.data ?? []).map((i) => i.name),
      symptom: mostFrequent(symptoms.data ?? [], "symptom"),
      eventTitle: mostFrequent(allEvents.data ?? [], "title"),
      ...(v && {
        doctor: v.doctor,
        specialty: v.specialty,
        place: v.place,
        room: v.room,
        purpose: v.purpose,
      }),
    };
    const byDoctor: Record<string, Record<string, string>> = {};
    for (const d of v?.doctors ?? []) {
      byDoctor[d.doctor.toLowerCase()] = { specialty: d.specialty, place: d.place, room: d.room };
    }
    const fills: Fills = { doctor: byDoctor };
    return { choices, suggestions, fills, people: people.data ?? [], cabinet: cabinet.data ?? [] };
  }, [people.data, conditions.data, allEvents.data, symptoms.data, cabinet.data, visits.data]);
}

/** Distinct values of one field (case-insensitive), most frequent first. */
function mostFrequent(rows: Row[], field: string): string[] {
  const count = new Map<string, { label: string; n: number }>();
  for (const e of rows) {
    const label = String(e[field] ?? "").trim();
    const hit = count.get(label.toLowerCase());
    if (hit) hit.n += 1;
    else if (label) count.set(label.toLowerCase(), { label, n: 1 });
  }
  return [...count.values()].sort((a, b) => b.n - a.n).map((x) => x.label);
}

/** Query keys refreshed after any health change (lists, doses, profile, cabinet, costs). */
export const HEALTH_INVALIDATE = [["health"], ["cabinet"], ["finance"]];
