import type { DeepTaskKind } from "./api";

const roadmapPattern =
  /(로드맵|학습\s*(계획|경로|순서)|커리큘럼|무엇부터\s*(배우|공부)|(?:공부|전체)\s*계획|다시\s*짜|단계별\s*계획)/i;
const researchPattern =
  /(자료\s*(조사|탐색|검색)|공식\s*(자료|문서|레퍼런스)|레퍼런스\s*(조사|탐색)|외부.{0,12}(최신\s*)?자료.{0,12}(찾|비교)|출처.{0,20}(확인\s*날짜|자료)|research|리서치)/i;
const impactPattern =
  /(영향(도|을|이|은|는)?|파급|사이드\s*이펙트|side\s*effect|변경\s*범위|어디까지\s*(바뀌|변경)|한\s*파일만\s*고치면|모든\s*(참조|호출처))/i;
const deepExplanationPattern =
  /(깊게|심층|자세히|전체\s*(흐름|생명주기)|처음부터\s*끝까지|deep\s*dive|딥\s*다이브|파고들|아키텍처.{0,20}근거와\s*함께)/i;

const explicitShallowBoundaryPatterns = [
  /(?:전체\s*흐름|심층|깊게|자세히).{0,16}(?:말고|말하지\s*말고)/i,
  /로드맵.{0,16}(?:바꾸지|만들지|짜지).{0,8}말고/i,
  /(?:외부\s*)?자료.{0,16}(?:찾지|조사하지|검색하지).{0,8}말고/i,
  /(?:지금\s*보고\s*있는\s*)?(?:테스트|파일|함수)\s*(?:하나|한\s*개)(?:만|를|을)?/i,
];

/**
 * Routes only explicit requests for expensive analysis. Ordinary explanations
 * deliberately return null and stay on the existing grounded chat path.
 */
export function routeQuestionToDeepTask(question: string): DeepTaskKind | null {
  const normalized = question.trim();
  if (!normalized) return null;
  if (explicitShallowBoundaryPatterns.some((pattern) => pattern.test(normalized))) {
    return null;
  }
  if (roadmapPattern.test(normalized)) return "roadmap_proposal";
  if (researchPattern.test(normalized)) return "research_materials";
  if (impactPattern.test(normalized)) return "impact_analysis";
  if (deepExplanationPattern.test(normalized)) return "deep_explanation";
  return null;
}
