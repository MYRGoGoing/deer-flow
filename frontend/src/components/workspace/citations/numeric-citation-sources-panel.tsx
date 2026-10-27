"use client";

import { BookOpenTextIcon } from "lucide-react";

import type { NumberedCitation } from "@/core/citations/numeric-sources";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

export function NumericCitationSourcesPanel({
  className,
  sources,
}: {
  className?: string;
  sources: NumberedCitation[];
}) {
  const { t } = useI18n();

  if (sources.length === 0) {
    return null;
  }

  return (
    <details
      className={cn(
        "not-prose border-border/60 bg-muted/20 mt-2 rounded-md border text-xs",
        className,
      )}
    >
      <summary className="text-muted-foreground hover:text-foreground flex cursor-pointer list-none items-center gap-2 px-3 py-2 transition-colors [&::-webkit-details-marker]:hidden">
        <BookOpenTextIcon className="size-3.5 shrink-0" />
        <span className="font-medium">
          {t.citations.sourcesSummary(sources.length)}
        </span>
      </summary>
      <ol className="border-border/60 divide-border/60 max-h-80 divide-y overflow-y-auto overscroll-contain border-t">
        {sources.map((source) => (
          <li key={source.id} className="flex min-w-0 items-start gap-2 p-2">
            <span className="text-muted-foreground w-5 shrink-0 pt-1 text-right font-mono tabular-nums">
              {source.index}
            </span>
            <span className="min-w-0 flex-1">
              <span className="text-foreground block truncate font-medium">
                {source.title}
              </span>
              {(source.section ?? source.source) && (
                <span className="text-muted-foreground block truncate">
                  {[source.section, source.source].filter(Boolean).join(" · ")}
                </span>
              )}
            </span>
            <span className="text-muted-foreground shrink-0 pt-1">
              {t.citations.citeCount(source.count)}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}
