/**
 * Categories are two levels: main ones (Samochód) and their sub-categories
 * (Paliwo, Przegląd techniczny). Pickers list them in tree order and label
 * a sub-category "Samochód › Paliwo", so typing "samoch" finds the whole group.
 */
import type { Category } from "./api";

export const PATH_SEP = " › ";

export function indexById(cats: Category[]): Record<string, Category> {
  return Object.fromEntries(cats.map((c) => [c.id, c]));
}

const byName = (a: Category, b: Category) => a.name.localeCompare(b.name);

/** Main categories by name, each followed by its sub-categories. A sub-category
 * whose main one isn't in ``cats`` is listed as if it were a main one. */
export function treeOrder(cats: Category[]): Category[] {
  const ids = new Set(cats.map((c) => c.id));
  const out: Category[] = [];
  for (const main of cats.filter((c) => !c.parent_id || !ids.has(c.parent_id)).sort(byName)) {
    out.push(main, ...cats.filter((c) => c.parent_id === main.id).sort(byName));
  }
  return out;
}

/** "Samochód › Paliwo" for a sub-category, the name for a main one. */
export function categoryPath(cat: Category, byId: Record<string, Category>): string {
  const parent = cat.parent_id ? byId[cat.parent_id] : undefined;
  return parent ? `${parent.name}${PATH_SEP}${cat.name}` : cat.name;
}

/** Options for a Select, in tree order; ``all`` names the main categories. */
export function categoryOptions(cats: Category[], all: Category[] = cats): { value: string; label: string }[] {
  const byId = indexById(all);
  return treeOrder(cats).map((c) => ({ value: c.id, label: categoryPath(c, byId) }));
}

/** The main category a category belongs to (itself for a main one). */
export function mainOf(cat: Category, byId: Record<string, Category>): Category {
  return (cat.parent_id && byId[cat.parent_id]) || cat;
}
