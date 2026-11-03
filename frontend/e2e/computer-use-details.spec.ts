import { test, expect } from "@playwright/test";

test("project detail displays source content and the computer-use handoff", async ({ page }) => {
  let task: any = null;
  const project = { id: 900, full_name: "owner/tv", description: "TV cleanup", collected: true, favorite: false,
    stars: 10, forks: 2, language: "Python", tags: [], notes: "", study_status: "待研究", metadata: { html_url: "https://github.com/owner/tv" },
    readme: "# Features\nDisable unwanted TV apps over Wi-Fi.", images: [], snapshots: [], research_provider: "computer_use",
    summary: { mode: "source", notice: "现展示 README 中的具体资料", source_excerpt_fields: ["functions"],
      functions: [{ text: "Disable unwanted TV apps over Wi-Fi.", quote: "Disable unwanted TV apps over Wi-Fi.", source: "https://github.com/owner/tv#readme" }],
      innovations: [], use_cases: [], requirements: [] } };
  await page.route("**/api/projects?*", route => route.fulfill({ json: { items: [project], total: 1, languages: ["Python"] } }));
  await page.route("**/api/projects/900", route => route.fulfill({ json: { ...project, research_task: task } }));
  await page.route("**/api/projects/900/refresh", async route => {
    task = { job_id: "browser-task", status: "waiting_browser", stage: "等待 computer-use 执行器接手浏览器检索", prompt: "请使用 computer-use 完成项目研究" };
    await route.fulfill({ json: { job_id: task.job_id, provider: "computer_use" } });
  });
  await page.route("**/api/computer-use/jobs/browser-task/cancel", async route => {
    task = { ...task, status: "cancelled", stage: "computer-use 任务已取消" };
    await route.fulfill({ json: { ok: true } });
  });
  await page.goto("/");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await page.getByRole("button", { name: "我的项目", exact: true }).click();
  await page.getByRole("heading", { name: "tv", exact: true }).click();
  await expect(page.getByText("Disable unwanted TV apps over Wi-Fi.", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "用 computer-use 补全中文详情" }).click();
  await expect(page.locator(".computer-use-status").getByRole("status")).toContainText("等待 computer-use");
  await expect(page.getByRole("button", { name: "复制 computer-use 执行指令" })).toBeVisible();
  await page.getByRole("button", { name: "取消本次等待" }).click();
  await expect(page.locator(".computer-use-status").getByRole("status")).toHaveText("computer-use 任务已取消");
});
