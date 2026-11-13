import { describe, expect, it } from "vitest";

import type { ModelOption, Status } from "./api";
import { modelOptions, validChoice } from "./ModelPicker";

const model = (id: string, location: "cloud" | "local", vision = true): ModelOption => ({
  id,
  name: id,
  kind: "openai",
  model: id,
  location,
  vision,
});

const status = (documents: Status["documents"]): Status => ({
  can_use: true,
  configured: true,
  private_available: true,
  can_manage: false,
  chat_profile: null,
  local_profile: null,
  file_profile: null,
  models: [model("claude", "cloud"), model("text-only", "cloud", false), model("ollama", "local")],
  documents,
});

const ids = (l: ModelOption[]) => l.map((m) => m.id);

describe("modelOptions", () => {
  it("offers every model for text, local ones in a private conversation", () => {
    expect(ids(modelOptions(status("cloud"), { files: false, isPrivate: false }))).toEqual(["claude", "text-only", "ollama"]);
    expect(ids(modelOptions(status("cloud"), { files: false, isPrivate: true }))).toEqual(["ollama"]);
  });

  it("offers for files only models that read them and may get them", () => {
    expect(ids(modelOptions(status("cloud"), { files: true, isPrivate: false }))).toEqual(["claude", "ollama"]);
    expect(ids(modelOptions(status("local"), { files: true, isPrivate: false }))).toEqual(["ollama"]);
    expect(ids(modelOptions(status("off"), { files: true, isPrivate: false }))).toEqual([]);
  });
});

describe("validChoice", () => {
  it("drops picks that don't fit back to the default", () => {
    const picked = { text_profile_id: "claude", file_profile_id: "text-only" };
    expect(validChoice(picked, status("cloud"), false)).toEqual({ text_profile_id: "claude", file_profile_id: null });
    expect(validChoice(picked, status("cloud"), true)).toEqual({ text_profile_id: null, file_profile_id: null });
    expect(validChoice({ text_profile_id: "gone", file_profile_id: "ollama" }, status("cloud"), false)).toEqual({
      text_profile_id: null,
      file_profile_id: "ollama",
    });
  });
});
