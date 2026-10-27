"use client";

import { BookOpen } from "lucide-react";
import { useSearchParams } from "next/navigation";

import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

export function Welcome({
  className,
}: {
  className?: string;
  mode?: "ultra" | "pro" | "thinking" | "flash";
}) {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-full flex-col items-center justify-center gap-3 px-4 py-6 text-center sm:px-8",
        className,
      )}
    >
      <BookOpen className="size-7 text-emerald-700" />
      <h1 className="text-2xl font-semibold">
        {searchParams.get("mode") === "skill"
          ? t.welcome.createYourOwnSkill
          : "知识问答"}
      </h1>
      {searchParams.get("mode") === "skill" && (
        <p className="text-muted-foreground text-sm">
          {t.welcome.createYourOwnSkillDescription}
        </p>
      )}
    </div>
  );
}
