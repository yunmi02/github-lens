import { test, expect } from "@playwright/test";

test("move a project to the recycle bin and restore it after a page reload", async ({ page }) => {
  let trashed = false;
  const project = { id: 990, full_name: "owner/kept", description: "A saved project", language: "Python", stars: 20,
    forks: 2, archived: false, collected: true, favorite: true, tags: ["reading"], notes: "my note", study_status: "已读",
    metadata: { html_url: "https://github.com/owner/kept" }, summary: {}, fetched_at: "2026-11-02T00:00:00Z" };
  await page.route("**/api/projects?*", route => {
    const trashView = new URL(route.request().url()).searchParams.get("trash") === "true";
    return route.fulfill({ json: { items: trashView === trashed ? [{ ...project, trashed_at: trashed ? "2026-11-02T01:00:00Z" : null }] : [],
      total: trashView === trashed ? 1 : 0, languages: ["Python"], active_total: trashed ? 0 : 1, trash_total: trashed ? 1 : 0 } });
  });
  await page.route("**/api/projects/990", route => {
    expect(route.request().method()).toBe("DELETE");
    trashed = true;
    return route.fulfill({ json: { id: 990, message: "项目已移入回收站" } });
  });
  await page.route("**/api/projects/990/restore", route => {
    expect(route.request().method()).toBe("POST");
    trashed = false;
    return route.fulfill({ json: { id: 990, message: "项目已恢复到项目库" } });
  });
  await page.goto("/?view=projects");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await page.getByRole("button", { name: "将 owner/kept 移入回收站", exact: true }).click();
  await expect(page.getByRole("heading", { name: "kept", exact: true })).toHaveCount(0);
  await page.getByRole("tab", { name: /回收站/ }).click();
  await expect(page.getByRole("heading", { name: "owner/kept", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("tab", { name: /回收站/ })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "恢复项目", exact: true }).click();
  await expect(page.getByRole("heading", { name: "回收站为空" })).toBeVisible();
  await page.getByRole("tab", { name: /项目库/ }).click();
  await expect(page.getByRole("heading", { name: "kept", exact: true })).toBeVisible();
  await expect(page.getByText("已读", { exact: true })).toBeVisible();
  await expect(page.getByText("reading", { exact: true })).toBeVisible();
});
