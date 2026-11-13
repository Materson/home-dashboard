import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";

import pl from "@/i18n/pl.json";

import { ApiProblem, problemText } from "./api";
import { passwordIssue, roleLabel } from "./parts";

const t = ((key: string) => (pl as Record<string, string>)[key] ?? key) as unknown as TFunction;

describe("passwordIssue", () => {
  it("wants 10 characters, typed the same twice", () => {
    expect(passwordIssue({ password: "short", repeat: "short" })).toBe("short");
    expect(passwordIssue({ password: "long-enough-1", repeat: "long-enough-2" })).toBe("repeat");
    expect(passwordIssue({ password: "long-enough-1", repeat: "long-enough-1" })).toBeNull();
  });
});

describe("problemText", () => {
  it("translates the backend's code", () => {
    expect(problemText(t, new ApiProblem(422, "email_taken"))).toBe(pl["problem.email_taken"]);
    expect(problemText(t, new ApiProblem(422, "lose_admin"))).toBe(pl["problem.lose_admin"]);
  });

  it("lists the password rules a password broke", () => {
    const text = problemText(t, new ApiProblem(422, "password", ["password_too_short", "password_entirely_numeric"]));
    expect(text).toBe(`${pl["problem.password_too_short"]} ${pl["problem.password_entirely_numeric"]}`);
  });

  it("falls back for what it doesn't know", () => {
    expect(problemText(t, new ApiProblem(403, "whatever"))).toBe(pl["problem.forbidden"]);
    expect(problemText(t, new ApiProblem(500, "500"))).toBe(pl["problem.unknown"]);
    expect(problemText(t, new Error("network"))).toBe(pl["problem.unknown"]);
  });
});

describe("roleLabel", () => {
  it("names built-in roles in the reader's language, others as typed", () => {
    expect(roleLabel("Parent", t)).toBe("Rodzic");
    expect(roleLabel("Babcia", t)).toBe("Babcia");
  });
});
