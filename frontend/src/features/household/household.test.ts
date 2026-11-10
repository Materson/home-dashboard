import { describe, expect, it } from "vitest";

import { fmtQty } from "@/lib/format";

import { boughtGuess } from "./ShoppingList";
import { expiryStatus } from "./StockTab";

describe("boughtGuess", () => {
  it("takes the number from the list's quantity text", () => {
    expect(boughtGuess("2 opak.")).toBe("2");
    expect(boughtGuess("1,5 l")).toBe("1.5");
    expect(boughtGuess("")).toBe("1");
  });
});

describe("expiryStatus", () => {
  const today = new Date(2026, 10, 10);
  it("matches the server's bands", () => {
    expect(expiryStatus(null, today)).toBe("unknown");
    expect(expiryStatus("2026-11-09", today)).toBe("expired");
    expect(expiryStatus("2026-11-10", today)).toBe("soon");
    expect(expiryStatus("2026-11-13", today)).toBe("soon");
    expect(expiryStatus("2026-11-14", today)).toBe("ok");
  });
});

describe("fmtQty", () => {
  it("drops trailing zeros only", () => {
    expect(fmtQty("10.00")).toBe("10");
    expect(fmtQty("2.00")).toBe("2");
    expect(fmtQty("1.50")).toMatch(/^1[.,]5$/);
    expect(fmtQty(null)).toBe("—");
  });
});
