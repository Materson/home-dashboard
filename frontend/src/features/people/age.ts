/** Full months between an API birth date ("YYYY-MM-DD") and today, or null. */
export function ageInMonths(birthDate: string | null, today: Date = new Date()): number | null {
  if (!birthDate) return null;
  const [y, m, d] = birthDate.split("-").map(Number);
  let months = (today.getFullYear() - y) * 12 + (today.getMonth() + 1 - m);
  if (today.getDate() < d) months -= 1;
  return months;
}
