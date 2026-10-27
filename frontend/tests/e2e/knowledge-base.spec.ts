import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const sampleDocument = {
  path: "platform/rbft-consensus.md",
  category: "platform",
  filename: "rbft-consensus.md",
  file_type: "md",
  size: 1200,
  modified_at: "2026-09-15T00:00:00Z",
  index_status: "indexed",
  chunk_count: 6,
};
const question = "RBFT 共识如何保证交易的一致性？";

async function mockKnowledge(page: Page) {
  mockLangGraphAPI(page);
  await page.route("**/api/kb/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/status"))
      return route.fulfill({
        json: {
          state: "ready",
          document_count: 1,
          indexed_document_count: 1,
          chunk_count: 6,
          embedding_backend: "test-bge",
          embedding_dim: 512,
        },
      });
    if (url.pathname.endsWith("/versions"))
      return route.fulfill({
        json: [
          {
            version_id: "v1",
            created_at: "2026-09-15T00:00:00Z",
            action: "upload",
            size: 1200,
          },
        ],
      });
    if (url.pathname.endsWith("/documents"))
      return route.fulfill({ json: [sampleDocument] });
    if (url.pathname.endsWith("/search"))
      return route.fulfill({
        json: {
          query: url.searchParams.get("q"),
          elapsed_ms: 28.5,
          hits: [
            {
              chunk_id: "c1",
              doc_title: "RBFT 共识算法",
              source_file: sampleDocument.path,
              category: "platform",
              text: "通过多阶段投票保证交易一致性。",
              context_text: "RBFT 通过多阶段投票保证交易一致性，支持视图切换。",
              section_path: "RBFT / 共识流程",
              weak_evidence: false,
            },
          ],
        },
      });
    return route.fulfill({ json: { success: true, message: "操作完成" } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockKnowledge(page);
});

test("searches knowledge, previews a passage and hands the question to chat", async ({
  page,
}) => {
  await page.goto("/workspace/knowledge");
  await expect(
    page.getByRole("heading", { name: "知识检索", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("rbft-consensus.md", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: question, exact: true }).click();
  await expect(
    page.getByRole("button", { name: "RBFT 共识算法", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("1 条候选片段 · 检索耗时 29 ms")).toBeVisible();
  await page.getByRole("button", { name: "查看原文片段", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("RBFT 通过多阶段投票保证交易一致性，支持视图切换。", {
      exact: true,
    }),
  ).toBeVisible();
  await dialog.getByRole("link", { name: "带入问答" }).click();
  const input = page.getByPlaceholder("输入技术问题，查询文档依据");
  await expect(input).toHaveValue(question);
  await input.press("Enter");
  await expect(
    page.getByText("Hello from DeerFlow!", { exact: true }),
  ).toBeVisible();
});

test("filters by category and keeps the URL and search input in sync", async ({
  page,
}) => {
  await page.goto("/workspace/knowledge");
  await page.getByLabel("检索知识库", { exact: true }).fill("EVM");
  await page.getByRole("button", { name: "检索", exact: true }).click();
  await page.getByRole("button", { name: "智能合约", exact: true }).click();
  await expect(page).toHaveURL(/category=contract-dev/);
  await expect(page.getByLabel("检索知识库", { exact: true })).toHaveValue(
    "EVM",
  );
  await page.goBack();
  await expect(page.getByLabel("检索知识库", { exact: true })).toHaveValue(
    "EVM",
  );
});

test("supports upload, confirmed version restoration and deletion", async ({
  page,
}) => {
  await page.goto("/workspace/knowledge/documents");
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await page.getByLabel("文件", { exact: true }).setInputFiles({
    name: "guide.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Guide"),
  });
  const upload = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/kb/upload") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "上传并入库", exact: true }).click();
  await upload;
  await expect(page.getByRole("dialog")).toBeHidden();
  await page
    .getByRole("button", { name: "查看 rbft-consensus.md 的版本" })
    .click();
  await expect(page.getByRole("heading", { name: "版本记录" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "恢复", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "恢复", exact: true }).click();
  const restoration = page.waitForRequest(
    (request) =>
      request.url().endsWith("/versions/v1/restore") &&
      request.method() === "POST",
  );
  await page.getByRole("button", { name: "确认恢复", exact: true }).click();
  await restoration;
  await expect(
    page.getByRole("heading", { name: "恢复历史版本？" }),
  ).toBeHidden();
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "删除 rbft-consensus.md", exact: true })
    .click();
  const deletion = page.waitForRequest(
    (request) => request.method() === "DELETE",
  );
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await deletion;
});

test("shows backend errors and empty search results", async ({ page }) => {
  await page.route("**/api/kb/search?**", (route) =>
    route.fulfill({ status: 503, json: { detail: "知识库索引尚未就绪" } }),
  );
  await page.goto("/workspace/knowledge?q=RBFT");
  await expect(
    page.getByRole("alert").filter({ hasText: "知识库索引尚未就绪" }),
  ).toBeVisible();
  await page.route("**/api/kb/search?**", (route) =>
    route.fulfill({ json: { query: "RBFT", hits: [], elapsed_ms: 1 } }),
  );
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(page.getByText("未找到匹配片段", { exact: true })).toBeVisible();
});

test("mobile layout has no page overflow and provides navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workspace/knowledge");
  await expect(
    page.getByRole("heading", { name: "知识检索", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Toggle Sidebar" }).first().click();
  await expect(
    page.getByRole("link", { name: "文档库", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "文档库", exact: true }).click();
  // A table may scroll horizontally inside its container, never the page itself.
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
