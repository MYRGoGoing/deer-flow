import { maskMarkdownCode } from "./sources";

export type NumberedCitation = {
  id: string;
  index: number;
  title: string;
  section?: string;
  source?: string;
  count: number;
};

export type ParsedNumberedCitations = {
  sources: NumberedCitation[];
  byIndex: Map<number, NumberedCitation>;
  markdown: string;
  body: string;
};

const REFERENCE_HEADING_RE =
  /^\s*(?:#{1,6}\s+)?(?:参考来源|references?)\s*[：:]?\s*$/i;
const REFERENCE_ITEM_RE = /^\s*(?:[-*+]\s+)?\[?(\d{1,2})\]?\s+(.+?)\s*$/;
const CITATION_MARKER_RE = /\[(\d{1,2})\]/g;

export function extractNumberedCitations(
  markdown: string,
): ParsedNumberedCitations {
  if (!markdown) {
    return { sources: [], byIndex: new Map(), markdown, body: markdown };
  }

  const headingMatch = findLastReferenceHeading(markdown);
  if (!headingMatch) {
    return { sources: [], byIndex: new Map(), markdown, body: markdown };
  }

  const body = markdown.slice(0, headingMatch.index);
  const sources = parseReferences(markdown.slice(headingMatch.index));
  markUsedCitations(sources, body);
  const byIndex = new Map(sources.map((source) => [source.index, source]));

  return {
    sources: sources.filter((source) => source.count > 0),
    byIndex,
    markdown,
    body,
  };
}

export function renderPreparedNumberedCitations(
  parsed: ParsedNumberedCitations,
): string {
  if (parsed.sources.length === 0) {
    return parsed.markdown;
  }

  const knownIndexes = new Set(parsed.sources.map((source) => source.index));
  return parsed.body.replace(CITATION_MARKER_RE, (marker, index: string) =>
    knownIndexes.has(Number(index))
      ? `[citation:${index}](#kb-citation-${index})`
      : marker,
  );
}

function findLastReferenceHeading(markdown: string) {
  const lines = maskMarkdownCode(markdown).split("\n");
  let charactersAfterHeading = 0;

  for (let lineIndex = lines.length - 1; lineIndex >= 0; lineIndex -= 1) {
    charactersAfterHeading +=
      lines[lineIndex]!.length + (lineIndex === lines.length - 1 ? 0 : 1);

    if (!REFERENCE_HEADING_RE.test(lines[lineIndex]!)) {
      continue;
    }

    const headingOffset = markdown.length - charactersAfterHeading;
    if (parseReferences(markdown.slice(headingOffset)).length > 0) {
      return { index: headingOffset };
    }
  }

  return null;
}

function parseReferences(block: string): NumberedCitation[] {
  const sources: NumberedCitation[] = [];

  for (const line of block.split("\n").slice(1)) {
    const match = REFERENCE_ITEM_RE.exec(line);
    if (!match) {
      if (sources.length > 0 && line.trim().length > 0) {
        break;
      }
      continue;
    }

    const index = Number(match[1]);
    const [rawTitle, rawSection, rawSource] = match[2]!.split("|");
    const title = rawTitle?.trim();
    if (!title) {
      continue;
    }

    sources.push({
      id: `kb-citation-${index}`,
      index,
      title,
      section: rawSection?.trim() ?? undefined,
      source:
        rawSource?.replace(/^\s*(?:来源|Source)\s*:\s*/i, "").trim() ??
        undefined,
      count: 0,
    });
  }

  return sources;
}

function markUsedCitations(sources: NumberedCitation[], body: string) {
  const searchable = maskMarkdownCode(body);
  const counts = new Map<number, number>();

  for (const match of searchable.matchAll(CITATION_MARKER_RE)) {
    const index = Number(match[1]);
    counts.set(index, (counts.get(index) ?? 0) + 1);
  }

  for (const source of sources) {
    source.count = counts.get(source.index) ?? 0;
  }
}
