import { test, expect } from "@playwright/test";

test("GitHub token form masks input and applies verified configuration", async ({ page }) => {
  const fakeToken = "github_pat_test_only_not_a_real_credential_12345";
  await page.route("**/api/settings/github-token", async route => {
    expect(route.request().postDataJSON().token).toBe(fakeToken);
    await route.fulfill({ json: { github_authenticated: true, message: "GitHub Token 已验证并保存，立即生效",
      rate_limit: { core: { limit: 5000, remaining: 4999 }, search: { limit: 30, remaining: 29 } } } });
  });
  await page.goto("/");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await page.getByRole("button", { name: "偏好设置", exact: true }).click();
  const input = page.getByLabel("GitHub Token", { exact: true });
  await expect(input).toHaveAttribute("type", "password");
  await expect(page.getByRole("link", { name: "前往 GitHub 创建令牌" })).toHaveAttribute("href", /personal-access-tokens\/new/);
  await input.fill(fakeToken);
  await page.getByRole("button", { name: "验证并保存 Token" }).click();
  await expect(input).toHaveValue("");
  await expect(page.getByText("已配置 Token", { exact: true })).toBeVisible();
  await expect(page.getByText("验证时可用额度", { exact: false })).toContainText("4999/5000");
  await expect(page.locator("body")).not.toContainText(fakeToken);
});
