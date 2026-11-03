import { test, expect } from "@playwright/test";

test("auto-confirm agent associates every project and displays search evidence", async ({ page }) => {
  let automatic = false;
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  const image: any = { id: "auto-demo", filename: "auto-demo.png", status: "needs_review", text: "Two projects", error: "",
    candidates: [{ full_name: "owner/first", confirmed: false }, { full_name: "owner/second", confirmed: false }] };
  const sources = [{ title: "项目官方文档", url: "https://docs.example/project" }];
  await page.route("**/api/import-batches", route => route.fulfill({ json: [{ id: "auto-batch", source: "desktop", created_at: "2026-10-29T00:00:00Z", images: [image] }] }));
  await page.route("**/api/images/auto-demo/file", route => route.fulfill({ path: "e2e/fixtures/sample.png" }));
  await page.route("**/api/recognitions/auto-demo/research", route => route.fulfill({ json: { image, research: automatic ? {
    status: "completed", stage: "自动确认与补全完成", error: "", report: { mode: "auto_confirm", confirmed_count: 2,
      conclusion: "已自动关联 2 个项目，并逐个搜索补全详情", rejected: { "macos/windows": "操作系统名称组合，非项目仓库" },
      plan: { useful_info: ["截图介绍两个项目"] }, sources,
      projects: image.candidates.map((c: any, i: number) => ({ ...c, repo_id: i + 1, description: "完整项目详情", stars: 10,
        metadata: { html_url: `https://github.com/${c.full_name}` }, summary: { overview: { text: "DeepSeek 搜索补全的项目介绍" }, functions: [{ text: "支持图片解析" }] } })) }
    } : null } }));
  await page.route("**/api/recognitions/auto-demo/auto-confirm", async route => {
    automatic = true; image.status = "completed"; image.candidates.forEach((c: any) => c.confirmed = true);
    await route.fulfill({ json: { job_id: "auto-job", created: true } });
  });
  await page.goto("/");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await page.getByRole("button", { name: "截图导入", exact: true }).click();
  await expect(page.getByRole("button", { name: "自动处理全部待确认" })).toBeEnabled();
  await page.locator(".image-row").getByRole("button", { name: "确认项目" }).click();
  await page.getByRole("button", { name: "自动确认全部项目并补全" }).click();
  await expect(page.getByRole("button", { name: "已关联", exact: true })).toHaveCount(2);
  await expect(page.getByText("已自动关联", { exact: true })).toHaveCount(2);
  await expect(page.locator(".auto-confirm-result")).toContainText("已自动关联 2 个项目");
  await expect(page.getByText("已过滤 macos/windows", { exact: false })).toBeVisible();
  await page.getByText("搜索来源（1）").click();
  await expect(page.getByRole("link", { name: "项目官方文档" })).toHaveAttribute("href", sources[0].url);
  await page.locator(".auto-confirm-panel").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "../data/qa/auto-confirm-agent.png", fullPage: true });
  expect(errors).toEqual([]);
});
