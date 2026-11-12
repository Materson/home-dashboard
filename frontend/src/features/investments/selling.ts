/** Selling part of a holding: which purchases it comes from and what that
 *  part cost — the same way the server splits them (tested in selling.test.ts). */
import type { Lot } from "./api";

/** Purchases still held on ``day``, oldest first: the order they're sold in (FIFO). */
export function heldLots(lots: Lot[], day: string): Lot[] {
  return lots
    .filter((l) => !l.sold_on && l.bought_on <= day)
    .sort((a, b) => a.bought_on.localeCompare(b.bought_on)); // stable: same day keeps API order
}

export function heldQuantity(lots: Lot[]): number {
  return lots.reduce((sum, l) => sum + Number(l.quantity), 0);
}

/** What selling ``quantity`` from ``lots`` (in order) cost to buy: whole
 *  purchases at their price, the last one cut at its share, rounded to grosze. */
export function saleCost(lots: Lot[], quantity: number): number {
  let left = quantity;
  let cost = 0;
  for (const lot of lots) {
    if (left <= 1e-12) break;
    const held = Number(lot.quantity);
    const take = Math.min(held, left);
    const price = Number(lot.price_total);
    cost += take === held ? price : Math.round(((price * take) / held) * 100) / 100;
    left -= take;
  }
  return Math.round(cost * 100) / 100;
}
