import { describe, expect, it } from "vitest";

import i18n from "@/i18n";

describe("assistant translations", () => {
  it("resolve flat keys that contain dots (action kinds)", () => {
    expect(i18n.t("assistant.action.finance.transaction", { lng: "pl" })).toBe("Transakcja");
    expect(i18n.t("assistant.action.household.shopping", { lng: "pl" })).toBe("Lista zakupów");
    expect(i18n.t("assistant.status.doneAuto", { lng: "pl" })).toBe("dodano");
  });

  it("use Polish plural forms", () => {
    expect(i18n.t("assistant.sent.images", { lng: "pl", count: 2 })).toBe("2 pliki");
    expect(i18n.t("assistant.sent.images", { lng: "pl", count: 5 })).toBe("5 plików");
  });
});
