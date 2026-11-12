import { describe, expect, it } from "vitest";

import type { Lot } from "./api";
import { heldLots, heldQuantity, saleCost } from "./selling";

const lot = (id: string, bought_on: string, quantity: string, price_total: string, sold_on: string | null = null): Lot => ({
  id,
  bought_on,
  quantity,
  price_total,
  sold_on,
  sold_amount: sold_on ? "1" : null,
  price_currency: "PLN",
  price_foreign: null,
  price_rate: null,
  sold_currency: "PLN",
  sold_foreign: null,
  sold_rate: null,
  rate_overrides: {},
  notes: "",
});

describe("selling part of a holding", () => {
  const lots = [
    lot("b", "2026-08-01", "3", "30000"),
    lot("a", "2026-01-15", "2", "16000"),
    lot("sold", "2025-12-01", "1", "5000", "2026-02-01"),
    lot("later", "2026-11-20", "1", "12000"),
  ];

  it("takes what was held that day, oldest first", () => {
    expect(heldLots(lots, "2026-11-12").map((l) => l.id)).toEqual(["a", "b"]);
    expect(heldQuantity(heldLots(lots, "2026-11-12"))).toBe(5);
    expect(heldLots(lots, "2026-03-01").map((l) => l.id)).toEqual(["a"]);
  });

  it("costs the whole older purchase and a share of the next", () => {
    const held = heldLots(lots, "2026-11-12");
    expect(saleCost(held, 3)).toBe(26000); // 2 oz for 16 000 + 1 of 3 oz for 30 000
    expect(saleCost(held, 5)).toBe(46000);
    expect(saleCost([lot("x", "2026-01-01", "0.3", "30000")], 0.1)).toBe(10000);
    expect(saleCost(held, 0)).toBe(0);
  });
});
