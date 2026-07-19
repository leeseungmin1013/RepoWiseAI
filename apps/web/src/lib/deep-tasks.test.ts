import { describe, expect, it } from "vitest";

import { routeQuestionToDeepTask } from "./deep-tasks";

describe("routeQuestionToDeepTask", () => {
  it.each([
    ["이 저장소 학습 로드맵을 만들어 줘", "roadmap_proposal"],
    ["공식 자료 조사를 해 줘", "research_materials"],
    ["이 변경이 어디까지 영향을 주는지 알려 줘", "impact_analysis"],
    ["요청의 전체 흐름을 깊게 설명해 줘", "deep_explanation"],
  ])("routes explicit deep request %s", (question, expected) => {
    expect(routeQuestionToDeepTask(question)).toBe(expected);
  });

  it.each([
    "이 함수는 무슨 역할이야?",
    "현재 레슨을 설명해 줘",
    "이 코드의 위치가 어디야?",
    "다음 호출은 무엇이야?",
  ])("keeps ordinary question on regular chat: %s", (question) => {
    expect(routeQuestionToDeepTask(question)).toBeNull();
  });
});
