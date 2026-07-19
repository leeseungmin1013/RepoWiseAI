import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { DeepTaskKind } from "./api";
import { routeQuestionToDeepTask } from "./deep-tasks";

type RoutingFixture = {
  id: string;
  utterance: string;
  expected_route: "grounded" | "deep";
  expected_kind: DeepTaskKind | null;
};

const fixturePath = resolve(process.cwd(), "../../evals/deep_task_routing.jsonl");
const fixtures = readFileSync(fixturePath, "utf8")
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line) as RoutingFixture);

describe("deep task routing evaluation", () => {
  it.each(fixtures)("matches $id", (fixture) => {
    const actual = routeQuestionToDeepTask(fixture.utterance);
    expect(actual).toBe(fixture.expected_kind);
    expect(actual ? "deep" : "grounded").toBe(fixture.expected_route);
  });
});
