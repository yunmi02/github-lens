import { test, expect } from "@playwright/test";

test("job center distinguishes automatic browser activity from tasks still waiting", async ({ page }) => {
  await page.route("**/api/browser-service/status", route => route.fulfill({ json: {
    provider: "browser", online: true, waiting: 2, current_job: "active", error: "", requires_desktop_session: false,
  } }));
  await page.route("**/api/jobs", route => route.fulfill({ json: [
    { id: "waiting", kind: "auto_confirm", status: "waiting_browser", stage: "等待后台浏览器服务自动领取", created_at: "2026-11-02T00:00:00Z", attempts: 3, browser_attempts: 0 },
    { id: "active", kind: "computer_use", status: "browser_running", stage: "浏览器核对项目", created_at: "2026-11-02T00:00:00Z", attempts: 0, browser_attempts: 1 },
  ] }));
  await page.goto("/?view=jobs");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await expect(page.getByText("后台浏览器服务已在线", { exact: true })).toBeVisible();
  const waiting = page.locator(".job-row").filter({ hasText: "等待后台浏览器服务自动领取" });
  await expect(waiting.locator(".spin")).toHaveCount(0);
  await expect(waiting).toContainText("浏览器已尝试 0 次");
  await expect(page.locator(".job-row").filter({ hasText: "浏览器核对项目" }).locator(".spin")).toHaveCount(1);
});

test("job center explains queue-wide cooldown and scheduled recovery", async ({ page }) => {
  await page.route("**/api/browser-service/status", route => route.fulfill({ json: {
    provider: "browser", online: true, status: "cooldown", waiting: 4, current_job: null,
    cooldown_until: "2026-11-02T14:00:00Z", error: "github.com 网页限流（HTTP 429），整个浏览器队列冷却后自动继续",
  } }));
  await page.route("**/api/jobs", route => route.fulfill({ json: [
    { id: "cooling", kind: "auto_confirm", status: "waiting_browser", error: "网页限流", stage: "等待冷却", created_at: "2026-11-02T00:00:00Z", available_at: "2026-11-02T13:00:00Z", browser_attempts: 1 },
  ] }));
  await page.goto("/?view=jobs");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await expect(page.getByText("浏览器服务在线 · 网页限流冷却中", { exact: true })).toBeVisible();
  await expect(page.locator(".browser-service-banner")).toContainText("预计恢复");
  await expect(page.locator(".browser-service-banner")).toContainText("整个队列暂停网页请求");
  await expect(page.locator(".job-row")).toContainText("下次重试不早于");
  await expect(page.locator(".job-row .spin")).toHaveCount(0);
});
