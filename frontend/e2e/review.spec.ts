import { test, expect } from "@playwright/test";

test("confirmed screenshot leaves pending list while alternatives remain accessible", async ({ page }) => {
  const image = {
    id: "review-regression", filename: "review-regression.png", status: "needs_review",
    error: "", text: "OCR toolkit", created_at: "2026-10-29T00:00:00Z",
    candidates: [
      { full_name: "owner/repo", confirmed: false, evidence: "待核对" },
      { full_name: "owner/alternative", confirmed: false, evidence: "搜索备选" },
    ],
    research: { status: "completed", stage: "研究完成，等待确认", error: "" },
  };
  await page.route("**/api/import-batches", route => route.fulfill({ json: [
    { id: "review-batch", source: "desktop", created_at: image.created_at, images: [image] },
  ] }));
  await page.route("**/api/images/review-regression/file", route => route.fulfill({ path: "e2e/fixtures/sample.png" }));
  await page.route("**/api/recognitions/review-regression/research", route => route.fulfill({ json: {
    image, research: { status: "completed", stage: "研究完成，等待确认", report: { conclusion: "等待确认" } },
  } }));
  await page.route("**/api/recognitions/review-regression/confirm", async route => {
    expect(route.request().postDataJSON().full_name).toBe("owner/repo");
    image.status = "completed";
    image.candidates[0].confirmed = true;
    await route.fulfill({ json: { job_id: "confirmed-job" } });
  });
  await page.goto("/");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await page.getByRole("button", { name: "截图导入", exact: true }).click();
  await page.getByRole("button", { name: "待处理 (1)", exact: true }).click();
  await page.locator(".image-row").getByRole("button", { name: "确认项目" }).click();
  await page.locator(".candidate").filter({ hasText: "owner/repo" }).getByRole("button", { name: "确认此项目" }).click();
  await expect(page.locator(".image-row")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "待处理", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "全部", exact: true }).click();
  await expect(page.locator(".image-row .status")).toHaveText("已完成");
  await expect(page.locator(".image-description p")).toHaveText("owner/repo");
  await page.locator(".image-row").getByRole("button", { name: "查看详情" }).click();
  await expect(page.getByRole("button", { name: "已关联", exact: true })).toBeDisabled();
  await expect(page.locator(".candidate").filter({ hasText: "owner/alternative" }).getByRole("button", { name: "确认此项目" })).toBeEnabled();
  await expect(page.locator(".research-conclusion")).toContainText("截图已关联项目");
});
