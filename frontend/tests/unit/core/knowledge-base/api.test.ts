import { beforeEach, describe, expect, rs, test } from "@rstest/core";

rs.mock("@/core/api/fetcher", () => ({ fetch: rs.fn() }));
rs.mock("@/core/config", () => ({ getBackendBaseURL: () => "" }));

import { fetch } from "@/core/api/fetcher";
import {
  getKnowledgeDocuments,
  searchKnowledge,
  uploadKnowledgeDocument,
} from "@/core/knowledge-base/api";
import {
  categoryLabel,
  knowledgeChatHref,
} from "@/core/knowledge-base/catalog";

const mockFetch = rs.mocked(fetch);
beforeEach(() => {
  mockFetch.mockReset();
});

describe("knowledge-base API", () => {
  test("encodes queries and categories and forwards cancellation", async () => {
    mockFetch.mockResolvedValueOnce(
      Response.json({ query: "RBFT & EVM", hits: [], elapsed_ms: 12 }),
    );
    const controller = new AbortController();
    await searchKnowledge("RBFT & EVM", "contract-dev", controller.signal);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/kb/search?q=RBFT+%26+EVM&category=contract-dev",
      { signal: controller.signal },
    );
  });
  test("surfaces permission and index errors without pretending the library is empty", async () => {
    mockFetch.mockResolvedValueOnce(
      Response.json({ detail: "Permission denied" }, { status: 403 }),
    );
    await expect(getKnowledgeDocuments()).rejects.toThrow(
      "当前账号没有此操作的知识库权限",
    );
    mockFetch.mockResolvedValueOnce(
      Response.json({ detail: "索引尚未就绪" }, { status: 503 }),
    );
    await expect(searchKnowledge("RBFT", "")).rejects.toThrow("索引尚未就绪");
  });
  test("uploads a real multipart file using the authenticated fetcher", async () => {
    mockFetch.mockResolvedValueOnce(
      Response.json({ success: true, message: "ok" }),
    );
    const file = new File(["# RBFT"], "guide.md", { type: "text/markdown" });
    await uploadKnowledgeDocument(file, "platform");
    const [url, init] = mockFetch.mock.calls[0]!;
    expect(url).toBe("/api/kb/upload");
    expect(init?.method).toBe("POST");
    expect((init?.body as FormData).get("category")).toBe("platform");
    expect(((init?.body as FormData).get("file") as File).name).toBe(
      "guide.md",
    );
  });
  test("uses readable categories and a safely encoded chat handoff", () => {
    expect(categoryLabel("platform")).toBe("平台与共识");
    expect(categoryLabel("custom")).toBe("custom");
    expect(
      new URL(
        knowledgeChatHref("RBFT & 一致性？"),
        "http://localhost",
      ).searchParams.get("question"),
    ).toBe("RBFT & 一致性？");
  });
});
