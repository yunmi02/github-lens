import { test, expect } from "@playwright/test";

test("Chinese project details and purpose categories support search and manual correction", async ({ page }) => {
  const project: any = { id: 950, full_name: "owner/papers", description: "Translate academic papers to Chinese.",
    display_description: "将学术论文翻译成中文并保留公式。", language: "Python", stars: 20, forks: 1,
    collected: true, favorite: false, archived: false, tags: [], notes: "", study_status: "待研究",
    categories: ["research"], category_labels: ["学术与科研"], keywords: ["论文翻译"],
    category_options: [{ id: "research", label: "学术与科研" }, { id: "documents", label: "文档与知识" }],
    summary_health: { complete: true }, metadata: { html_url: "https://github.com/owner/papers", topics: [] },
    summary: { mode: "ai", overview: { text: "将学术论文翻译成中文并保留公式。" },
      functions: [{ text: "保留公式与论文结构", quote: "Preserve academic equations.", source: "https://github.com/owner/papers" }],
      use_cases: [], innovations: [], requirements: [] }, images: [], snapshots: [], fetched_at: "2026-11-03T00:00:00Z" };
  let categorySeen = false;
  let keywordsSeen = false;
  await page.route("**/api/projects?*", route => {
    categorySeen ||= new URL(route.request().url()).searchParams.get("category") === "research";
    return route.fulfill({ json: { items: [project], total: 1, languages: ["Python"], categories: [{ id: "research", label: "学术与科研", count: 1 }] } });
  });
  await page.route("**/api/projects/950", route => {
    if (route.request().method() === "PATCH") {
      const patch = route.request().postDataJSON();
      keywordsSeen ||= patch.keywords?.includes("文献阅读") || false;
      Object.assign(project, patch);
    }
    return route.fulfill({ json: project });
  });
  await page.goto("/?view=projects");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await page.getByRole("button", { name: /学术与科研/ }).click();
  await expect.poll(() => categorySeen).toBeTruthy();
  await page.getByLabel("搜索项目").fill("论文 翻译");
  await expect(page.getByText("将学术论文翻译成中文并保留公式。", { exact: true })).toBeVisible();
  await page.getByRole("heading", { name: "papers", exact: true }).click();
  await expect(page.locator(".detail-heading")).toContainText("将学术论文翻译成中文并保留公式。");
  await expect(page.getByText("保留公式与论文结构", { exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "文档与知识", exact: true }).check();
  await page.getByLabel("检索关键词", { exact: true }).fill("论文翻译, 文献阅读");
  await page.getByRole("button", { name: "保存检索关键词", exact: true }).click();
  await expect.poll(() => keywordsSeen).toBeTruthy();
  await page.getByText("查看官方原始简介", { exact: true }).click();
  await expect(page.getByText(project.description, { exact: true })).toBeVisible();
});
