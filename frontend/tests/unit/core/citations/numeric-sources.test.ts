import { describe, expect, it } from "@rstest/core";

import {
  extractNumberedCitations,
  renderPreparedNumberedCitations,
} from "@/core/citations/numeric-sources";

const markdown = [
  "RBFT is the consensus used here [1].",
  "It supports SM2 and SM3 [1][2].",
  "`[3] should stay inert`",
  "",
  "参考来源：",
  "[1] RBFT Overview | Consensus | 来源: internal corpus",
  "[2] Cryptography | National Algorithms | 来源: public material",
  "[3] Unused Source | Other | 来源: ignored",
].join("\n");

describe("extractNumberedCitations", () => {
  it("parses the reference list and counts markers outside code", () => {
    const parsed = extractNumberedCitations(markdown);

    expect(parsed.sources).toHaveLength(2);
    expect(parsed.sources[0]).toMatchObject({
      index: 1,
      title: "RBFT Overview",
      section: "Consensus",
      source: "internal corpus",
      count: 2,
    });
    expect(parsed.sources[1]).toMatchObject({
      index: 2,
      title: "Cryptography",
      count: 1,
    });
    expect(parsed.body).toBe(markdown.slice(0, markdown.indexOf("参考来源")));
  });

  it("prepares only known and used citations for rendering", () => {
    const prepared = renderPreparedNumberedCitations(
      extractNumberedCitations(markdown),
    );

    expect(prepared).toContain("[citation:1](#kb-citation-1)");
    expect(prepared).toContain("[citation:2](#kb-citation-2)");
    expect(prepared).toContain("`[3] should stay inert`");
    expect(prepared).not.toContain("参考来源");
    expect(prepared).not.toContain("[citation:3](#kb-citation-3)");
  });

  it("does not activate references that were never cited", () => {
    const parsed = extractNumberedCitations(
      "No inline marker\n\n参考来源\n[1] Doc",
    );

    expect(parsed.sources).toEqual([]);
    expect(renderPreparedNumberedCitations(parsed)).toContain("[1] Doc");
  });

  it("accepts markdown bullet lists produced by the answer model", () => {
    const parsed = extractNumberedCitations(
      [
        "HVM uses @Contract on the class [1].",
        "",
        "参考来源：",
        "- [1] HVM 合约开发指南 | 合约基本结构 | contract-dev/hvm-guide.md",
      ].join("\n"),
    );

    expect(parsed.sources).toEqual([
      {
        id: "kb-citation-1",
        index: 1,
        title: "HVM 合约开发指南",
        section: "合约基本结构",
        source: "contract-dev/hvm-guide.md",
        count: 1,
      },
    ]);
    expect(renderPreparedNumberedCitations(parsed)).toContain(
      "[citation:1](#kb-citation-1)",
    );
  });
});
