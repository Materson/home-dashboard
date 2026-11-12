import { describe, expect, it } from "vitest";

import type { Category } from "./api";
import { categoryOptions, mainOf, treeOrder } from "./categoryTree";

const cat = (id: string, name: string, parent_id: string | null = null): Category => ({
  id,
  key: id,
  name,
  kind: "expense",
  parent_id,
  color: "#868e96",
  is_system: false,
  used: 0,
});

const car = cat("car", "Samochód");
const fuel = cat("fuel", "Paliwo", "car");
const check = cat("check", "Przegląd techniczny", "car");
const health = cat("health", "Zdrowie");
const meds = cat("meds", "Leki", "health");
const all = [meds, check, health, fuel, car];

describe("category tree", () => {
  it("lists main categories by name, each followed by its sub-categories", () => {
    expect(treeOrder(all).map((c) => c.id)).toEqual(["car", "fuel", "check", "health", "meds"]);
  });

  it("labels sub-categories with their main one, so searching finds the group", () => {
    expect(categoryOptions(all).map((o) => o.label)).toEqual([
      "Samochód",
      "Samochód › Paliwo",
      "Samochód › Przegląd techniczny",
      "Zdrowie",
      "Zdrowie › Leki",
    ]);
  });

  it("shows a sub-category whose main one is filtered out on its own, still labelled", () => {
    // (sorted by its own name: Leki before Samochód)
    expect(categoryOptions([meds, car], all)).toEqual([
      { value: "meds", label: "Zdrowie › Leki" },
      { value: "car", label: "Samochód" },
    ]);
  });

  it("finds the main category", () => {
    const byId = Object.fromEntries(all.map((c) => [c.id, c]));
    expect(mainOf(fuel, byId)).toBe(car);
    expect(mainOf(car, byId)).toBe(car);
  });
});
