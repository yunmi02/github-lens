import { test, expect } from "@playwright/test";
import fs from "node:fs";

test("pending image can request agent research and inspect cited findings", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("管理员密码").fill("e2e-test-password-123");
  await page.getByRole("button", { name: "登录工作空间" }).click();
  await expect(
    page.getByRole("heading", { name: "从截图，到下一次灵感" }),
  ).toBeVisible();
  const batch = (await (await page.request.post("/api/import-batches")).json())
    .id;
  const upload = await page.request.post(
    `/api/import-batches/${batch}/images`,
    {
      multipart: {
        file: {
          name: "agent-sample.png",
          mimeType: "image/png",
          buffer: Buffer.concat([
            fs.readFileSync("e2e/fixtures/sample.png"),
            Buffer.from("unique-research-" + Date.now()),
          ]),
        },
      },
    },
  );
  const imageId = (await upload.json()).id;
  await expect
    .poll(
      async () => {
        const r = await page.request.get(`/api/import-batches/${batch}`);
        return (await r.json()).images[0].status;
      },
      { timeout: 20000 },
    )
    .toBe("failed");
  let completed = false;
  const repo = {
    repo_id: 262296122,
    full_name: "PaddlePaddle/PaddleOCR",
    description: "OCR toolkit",
    stars: 100,
    language: "Python",
    metadata: {
      html_url: "https://github.com/PaddlePaddle/PaddleOCR",
      created_at: "2020-05-08T10:38:16Z",
    },
    summary: {
      overview: { text: "可提取图片文字的 OCR 工具" },
      functions: [{ text: "识别截图中的文字" }],
    },
    evidence: "联网搜索发现的相关仓库，待确认",
    confirmed: false,
  };
  await page.route(`**/api/recognitions/${imageId}/research`, async (route) => {
    if (route.request().method() === "POST") {
      completed = true;
      await route.fulfill({ json: { job_id: "test-research", created: true } });
      return;
    }
    await route.fulfill({
      json: {
        image: {
          id: imageId,
          filename: "agent-sample.png",
          status: "needs_review",
          error: "",
          text: "OCR toolkit",
          candidates: completed ? [repo] : [],
        },
        research: completed
          ? {
              status: "completed",
              stage: "研究完成，等待确认",
              report: {
                plan: { useful_info: ["图中介绍一个 OCR 工具"] },
                queries: ["PaddleOCR GitHub"],
                projects: [repo],
                sources: [
                  {
                    title: "PaddleOCR 官方仓库",
                    url: "https://github.com/PaddlePaddle/PaddleOCR",
                  },
                ],
                conclusion: "已核实 1 个候选仓库，请对照截图确认关联。",
              },
            }
          : null,
      },
    });
  });
  await page.getByRole("button", { name: "截图导入", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "研究全部待处理" }),
  ).toBeVisible();
  await page
    .locator(".image-row")
    .filter({ has: page.locator(`img[src="/api/images/${imageId}/file"]`) })
    .getByRole("button", { name: "确认项目" })
    .click();
  await page.getByRole("button", { name: "让智能体搜索项目详情" }).click();
  await expect(
    page.getByRole("heading", { name: "已核实的项目详情" }),
  ).toBeVisible();
  await expect(page.getByText("图中介绍一个 OCR 工具")).toBeVisible();
  await expect(page.getByRole("button", { name: "确认此项目" })).toBeEnabled();
  await page.getByText("搜索来源（1）").click();
  await expect(
    page.getByRole("link", { name: "PaddleOCR 官方仓库" }),
  ).toHaveAttribute("href", "https://github.com/PaddlePaddle/PaddleOCR");
  await page.screenshot({
    path: "../data/qa/research-agent.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
