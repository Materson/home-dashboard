/** Splitting an amount between people — mirrors the server's rules
 *  (apps/finance/services.py: equal_split / normalize_shares). */

export type Share = { person_id: string; amount: string };

const toCents = (value: string): number => Math.round(Number(value || "0") * 100);
const fromCents = (cents: number): string => (cents / 100).toFixed(2);

/** 100 for 3 people → 33.34 + 33.33 + 33.33 (every cent accounted for). */
export function equalSplit(amount: string, personIds: string[]): Share[] {
  if (!personIds.length) return [];
  const cents = toCents(amount);
  const base = Math.floor(cents / personIds.length);
  const rest = cents - base * personIds.length;
  return personIds.map((person_id, i) => ({ person_id, amount: fromCents(base + (i < rest ? 1 : 0)) }));
}

/** Parts add up to the amount and none is zero (or nobody is chosen). */
export function sharesValid(amount: string, shares: Share[]): boolean {
  if (shares.length <= 1) return true;
  return shares.every((s) => toCents(s.amount) > 0) && shares.reduce((n, s) => n + toCents(s.amount), 0) === toCents(amount);
}

/** How much is still to assign (negative = too much). */
export function remainder(amount: string, shares: Share[]): string {
  return fromCents(toCents(amount) - shares.reduce((n, s) => n + toCents(s.amount), 0));
}
