import { describe, expect, it } from "vitest";

import { safeNextPath } from "./auth";

describe("safeNextPath", () => {
  it("preserves internal paths including query and hash", () => {
    expect(safeNextPath("/account?tab=usage#limits")).toBe(
      "/account?tab=usage#limits",
    );
  });

  it.each([
    "https://evil.example/steal",
    "//evil.example/steal",
    "javascript:alert(1)",
    "account",
    null,
  ])("rejects unsafe redirect %s", (value) => {
    expect(safeNextPath(value)).toBe("/");
  });
});