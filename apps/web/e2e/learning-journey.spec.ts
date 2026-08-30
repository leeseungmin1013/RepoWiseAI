import { expect, test } from "@playwright/test";

const question = "이 레슨의 핵심 실행 순서를 한 문장으로 설명해줘";

test("assessment timeout, refresh restore, and remediation return", async ({ page }) => {
  await page.goto("/");
  const startLearning = page.getByRole("button", { name: /깊이 배우기/ });
  await expect(startLearning).toBeVisible({ timeout: 60_000 });
  await startLearning.click();

  await expect(page.getByText("맞춤 학습 진단")).toBeVisible();
  const composer = page.getByPlaceholder("현재 코드에서 막힌 부분을 질문하세요");
  await expect(composer).toBeVisible({ timeout: 60_000 });

  await composer.fill(question);
  await page.getByRole("button", { name: "질문 보내기" }).click();
  await expect(page.getByText(question, { exact: true })).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: "작은 예제" }).click();
  const returnButton = page.getByRole("button", { name: /원래 레슨으로 돌아가기/ });
  await expect(returnButton).toBeVisible({ timeout: 60_000 });

  await page.reload();
  await expect(startLearning).toBeVisible({ timeout: 60_000 });
  await startLearning.click();

  await expect(page.getByText(question, { exact: true })).toBeVisible({ timeout: 60_000 });
  await expect(returnButton).toBeVisible({ timeout: 60_000 });
  await returnButton.click();
  await expect(returnButton).toBeHidden({ timeout: 60_000 });
  await expect(composer).toBeVisible();
});