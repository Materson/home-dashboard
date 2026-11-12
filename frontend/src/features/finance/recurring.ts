/** Repeating payments: helpers shared by the list and the edit window. */

/** "FREQ=MONTHLY;INTERVAL=3" → "quarterly" (labels in finance.repeat.*). */
export function repeatKind(rrule: string): string {
  if (rrule.includes("FREQ=WEEKLY")) return "weekly";
  if (rrule.includes("FREQ=YEARLY")) return "yearly";
  if (rrule.includes("FREQ=MONTHLY")) return rrule.includes("INTERVAL=3") ? "quarterly" : "monthly";
  return "custom";
}
