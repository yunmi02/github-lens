import { test, expect } from "@playwright/test";

test("login, workspace navigation, imports and isolated phone upload", async ({
  page,
  browser,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await expect(
    page.getByRole("heading", { name: "从截图，到下一次灵感" }),
  ).toBeVisible();
  await page.screenshot({ path: "../data/qa/workspace.png", fullPage: true });
  await page.getByRole("button", { name: "我的项目", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "我的项目", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "偏好设置" }).click();
  await expect(
    page.getByRole("heading", { name: "自动发现规则" }),
  ).toBeVisible();
  await page.getByLabel("每日运行").uncheck();
  await page.getByRole("button", { name: "保存规则" }).click();
  await expect(page.getByRole("status")).toContainText("自动发现规则已保存");
  await page.getByRole("button", { name: "截图导入", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "截图导入", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "手机上传", exact: true }).click();
  await page.getByLabel("手机可访问的系统地址").fill("http://127.0.0.1:8011");
  await page.getByRole("button", { name: "生成临时二维码" }).click();
  await expect(page.getByAltText("手机上传二维码")).toBeVisible();
  const phoneUrl = await page
    .getByRole("link", { name: "在浏览器测试上传页" })
    .getAttribute("href");
  const phoneContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const phone = await phoneContext.newPage();
  await phone.goto(phoneUrl!);
  await expect(phone.getByRole("button", { name: "选择图片" })).toBeVisible();
  await phone
    .locator("input[type=file]")
    .first()
    .setInputFiles("e2e/fixtures/sample.png");
  await expect(
    phone.getByRole("heading", { name: "本次上传回执" }),
  ).toBeVisible();
  await phone.screenshot({ path: "../data/qa/mobile.png", fullPage: true });
  const forbidden = await phoneContext.request.get(
    "http://127.0.0.1:8011/api/projects",
  );
  expect(forbidden.status()).toBe(401);
  await phoneContext.close();
  await page.getByRole("button", { name: "撤销二维码及上传会话" }).click();
  expect(errors).toEqual([]);
});
