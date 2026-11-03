import { test, expect } from "@playwright/test";

test("password settings validate confirmation and clear secrets after success", async ({ page }) => {
  let changed = false;
  await page.route("**/api/auth/password", async route => {
    expect(route.request().postDataJSON()).toEqual({ current_password: "test-current-password", new_password: "test-new-password-123" });
    changed = true;
    await route.fulfill({ json: { ok: true } });
  });
  await page.goto("/?view=settings");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  const current = page.getByLabel("当前密码", { exact: true });
  const next = page.getByLabel("新密码", { exact: true });
  const confirm = page.getByLabel("确认新密码", { exact: true });
  await expect(current).toHaveAttribute("type", "password");
  await current.fill("test-current-password");
  await next.fill("test-new-password-123");
  await confirm.fill("different-password-123");
  await page.getByRole("button", { name: "修改密码", exact: true }).click();
  await expect(page.getByText("两次输入的新密码不一致", { exact: true })).toBeVisible();
  expect(changed).toBeFalsy();
  await confirm.fill("test-new-password-123");
  await page.getByRole("button", { name: "修改密码", exact: true }).click();
  await expect(page.getByText("密码已修改，其他设备的旧登录已失效", { exact: true })).toBeVisible();
  await expect(current).toHaveValue("");
  await expect(next).toHaveValue("");
  await expect(confirm).toHaveValue("");
});
