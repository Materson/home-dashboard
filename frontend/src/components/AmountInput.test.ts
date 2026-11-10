import { describe, expect, it } from "vitest";
import { isPositiveAmount, toApi, toInput } from "./AmountInput";

describe("AmountInput conversions", () => {
  it("turns typed comma decimals into dot-decimal API strings", () => {
    expect(toApi("12,5")).toBe("12.5");
    expect(toApi("12,")).toBe("12.");
    expect(toApi("1 234,50")).toBe("1234.50");
    expect(toApi(12.5)).toBe("12.5");
    expect(toApi("")).toBe("");
  });

  it("shows API strings as numbers, empty stays empty", () => {
    expect(toInput("150.00")).toBe(150);
    expect(toInput("")).toBe("");
  });

  it("accepts only positive amounts", () => {
    expect(isPositiveAmount(toApi("0,01"))).toBe(true);
    expect(isPositiveAmount("")).toBe(false);
    expect(isPositiveAmount("0")).toBe(false);
  });
});
