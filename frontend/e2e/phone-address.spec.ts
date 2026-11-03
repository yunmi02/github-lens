import { test, expect } from "@playwright/test";

test("a late address suggestion preserves the phone address entered by the user", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/network", async route => {
    await gate;
    await route.fulfill({ json: { configured: "http://127.0.0.1:8000", suggestions: [] } });
  });
  await page.goto("/");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await page.getByRole("button", { name: "手机上传", exact: true }).click();
  const address = page.getByLabel("手机可访问的系统地址");
  await address.fill("http://127.0.0.1:8011");
  const suggestion = page.waitForResponse("**/api/network");
  release();
  await suggestion;
  await page.getByRole("button", { name: "生成临时二维码" }).click();
  await expect(page.getByRole("link", { name: "在浏览器测试上传页" })).toHaveAttribute("href", /^http:\/\/127\.0\.0\.1:8011\/mobile#token=/);
  await expect(address).toHaveValue("http://127.0.0.1:8011");
  await page.getByRole("button", { name: "撤销二维码及上传会话" }).click();
});
