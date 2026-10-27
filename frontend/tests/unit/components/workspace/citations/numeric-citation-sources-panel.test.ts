import { describe, expect, it } from "@rstest/core";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { NumericCitationSourcesPanel } from "@/components/workspace/citations/numeric-citation-sources-panel";
import type { NumberedCitation } from "@/core/citations/numeric-sources";
import { I18nContext } from "@/core/i18n/context";
import { zhCN } from "@/core/i18n/locales/zh-CN";

const sources: NumberedCitation[] = [
  {
    id: "kb-citation-1",
    index: 1,
    title: "Platform Overview",
    section: "Core Features",
    source: "Example corpus",
    count: 2,
  },
];

describe("NumericCitationSourcesPanel", () => {
  it("renders nothing when there are no numeric citations", () => {
    const html = renderPanel([]);

    expect(html).toBe("");
  });

  it("renders numbered source metadata with citation counts", () => {
    const html = renderPanel(sources);

    expect(html).toContain("使用了 1 个来源");
    expect(html).toContain("Platform Overview");
    expect(html).toContain("Core Features · Example corpus");
    expect(html).toContain("2 次引用");
  });
});

function renderPanel(panelSources: NumberedCitation[]) {
  return renderToStaticMarkup(
    createElement(
      I18nContext.Provider,
      { value: { locale: "zh-CN", setLocale: () => undefined, t: zhCN } },
      createElement(NumericCitationSourcesPanel, { sources: panelSources }),
    ),
  );
}
