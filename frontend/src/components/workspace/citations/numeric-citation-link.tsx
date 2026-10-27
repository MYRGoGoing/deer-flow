"use client";

import { isValidElement, type ComponentProps, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import type { NumberedCitation } from "@/core/citations/numeric-sources";

export function createNumberedCitationLinkComponent(
  citationsByIndex: Map<number, NumberedCitation>,
) {
  return function NumberedCitationLink({
    href,
    ...props
  }: ComponentProps<"a">) {
    const index = Number(extractReactNodeText(props.children));
    const citation = citationsByIndex.get(index);

    if (!citation || href !== `#kb-citation-${index}`) {
      const { className, children } = props;
      return (
        <a {...props} href={href} className={className}>
          {children}
        </a>
      );
    }

    return (
      <HoverCard closeDelay={0} openDelay={0}>
        <HoverCardTrigger asChild>
          <button
            type="button"
            aria-label={`引用 ${citation.index}: ${citation.title}`}
            className="mx-0.5 inline-flex items-center align-baseline"
          >
            <Badge
              variant="secondary"
              className="hover:bg-secondary/80 h-5 cursor-pointer rounded-full px-1.5 py-0 font-mono text-[10px] leading-5 font-normal"
            >
              {citation.index}
            </Badge>
          </button>
        </HoverCardTrigger>
        <HoverCardContent className="w-80 p-3">
          <div className="space-y-2">
            <div className="flex min-w-0 items-start gap-2">
              <Badge
                variant="secondary"
                className="h-5 shrink-0 rounded-full px-1.5 py-0 font-mono text-[10px] leading-5"
              >
                {citation.index}
              </Badge>
              <h4 className="text-foreground min-w-0 flex-1 text-sm leading-tight font-medium">
                {citation.title}
              </h4>
            </div>
            {citation.section && (
              <p className="text-muted-foreground truncate text-xs">
                {citation.section}
              </p>
            )}
            {citation.source && (
              <p className="text-muted-foreground truncate text-xs">
                {citation.source}
              </p>
            )}
          </div>
        </HoverCardContent>
      </HoverCard>
    );
  };
}

function extractReactNodeText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(extractReactNodeText).join("");
  }
  if (isValidElement(node)) {
    const children = (node.props as { children?: ReactNode }).children;
    return children === undefined ? "" : extractReactNodeText(children);
  }
  return "";
}
