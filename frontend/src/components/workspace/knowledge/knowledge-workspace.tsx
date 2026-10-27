"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  ChevronRight,
  Database,
  FileText,
  FolderOpen,
  History,
  Loader2,
  type LucideIcon,
  MessageSquareText,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { SidebarTrigger } from "@/components/ui/sidebar";
import {
  deleteKnowledgeDocument,
  getKnowledgeDocuments,
  getKnowledgeStatus,
  getKnowledgeVersions,
  restoreKnowledgeVersion,
  searchKnowledge,
  uploadKnowledgeDocument,
  type KnowledgeDocument,
  type KnowledgeHit,
  type KnowledgeVersion,
} from "@/core/knowledge-base/api";
import {
  categoryLabel,
  formatDocumentSize,
  KNOWLEDGE_CATEGORIES,
  KNOWLEDGE_QUESTIONS,
  knowledgeChatHref,
} from "@/core/knowledge-base/catalog";
import { cn } from "@/lib/utils";

const queryRoot = ["knowledge-base"] as const;

function ErrorState({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 border-b border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200"
    >
      <ShieldAlert className="size-4 shrink-0" />
      <span className="min-w-0 flex-1 break-words">{error.message}</span>
      <Button size="sm" variant="outline" onClick={retry}>
        <RefreshCw className="size-3.5" />
        重试
      </Button>
    </div>
  );
}

function IndexBadge({ state }: { state: string }) {
  const ready = state === "ready" || state === "indexed";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 text-xs",
        ready
          ? "text-emerald-700 dark:text-emerald-400"
          : "text-amber-700 dark:text-amber-400",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          ready ? "bg-emerald-500" : "bg-amber-500",
        )}
      />
      {ready ? "已索引" : state === "stale" ? "待同步" : "未建索引"}
    </span>
  );
}

export function KnowledgeWorkspace({ view }: { view: "search" | "documents" }) {
  const router = useRouter();
  const params = useSearchParams();
  const query = params.get("q")?.trim() ?? "";
  const category = params.get("category") ?? "";
  const [editedDraft, setEditedDraft] = useState({ query, value: query });
  const draft = editedDraft.query === query ? editedDraft.value : query;
  const setDraft = (value: string) => setEditedDraft({ query, value });
  const [selectedHit, setSelectedHit] = useState<KnowledgeHit | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [versionDocument, setVersionDocument] =
    useState<KnowledgeDocument | null>(null);
  const [deleteDocument, setDeleteDocument] =
    useState<KnowledgeDocument | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<{
    document: KnowledgeDocument;
    version: KnowledgeVersion;
  } | null>(null);
  const [uploadCategory, setUploadCategory] = useState("platform");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const client = useQueryClient();
  const documents = useQuery({
    queryKey: [...queryRoot, "documents"],
    queryFn: ({ signal }) => getKnowledgeDocuments(signal),
    staleTime: 30_000,
    retry: 1,
  });
  const status = useQuery({
    queryKey: [...queryRoot, "status"],
    queryFn: ({ signal }) => getKnowledgeStatus(signal),
    staleTime: 30_000,
    retry: 1,
  });
  const results = useQuery({
    queryKey: [...queryRoot, "search", query, category],
    queryFn: ({ signal }) => searchKnowledge(query, category, signal),
    enabled: view === "search" && !!query,
    staleTime: 30_000,
    retry: false,
  });
  const versions = useQuery({
    queryKey: [...queryRoot, "versions", versionDocument?.path],
    queryFn: ({ signal }) => getKnowledgeVersions(versionDocument!, signal),
    enabled: !!versionDocument,
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: (action: () => Promise<{ message: string }>) => action(),
    onSuccess: async (data) => {
      toast.success(data.message);
      setUploadOpen(false);
      setUploadFile(null);
      setDeleteDocument(null);
      setRestoreTarget(null);
      await client.invalidateQueries({ queryKey: queryRoot });
    },
    onError: (error) => toast.error(error.message),
  });

  const categories = Array.from(
    new Set([
      ...KNOWLEDGE_CATEGORIES.map((item) => item.value),
      ...(documents.data ?? []).map((item) => item.category),
    ]),
  );
  const visibleDocuments = (documents.data ?? []).filter(
    (item) =>
      (!category || item.category === category) &&
      (!query ||
        `${item.filename} ${categoryLabel(item.category)}`
          .toLowerCase()
          .includes(query.toLowerCase())),
  );
  const basePath =
    view === "search"
      ? "/workspace/knowledge"
      : "/workspace/knowledge/documents";

  function navigate(nextQuery: string, nextCategory = category) {
    const search = new URLSearchParams();
    if (nextQuery.trim()) search.set("q", nextQuery.trim());
    if (nextCategory) search.set("category", nextCategory);
    router.push(`${basePath}${search.size ? `?${search}` : ""}`);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (draft.trim() === query) {
      if (query && view === "search") void results.refetch();
    } else navigate(draft);
  }

  return (
    <div className="bg-background text-foreground flex h-full min-h-0 flex-col">
      <header className="flex min-h-14 shrink-0 items-center justify-between gap-3 border-b px-4 sm:px-8">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <SidebarTrigger className="md:hidden" />
          <span className="text-muted-foreground hidden sm:inline">
            企业知识库
          </span>
          <ChevronRight className="text-muted-foreground hidden size-3.5 sm:block" />
          <span className="font-medium">
            {view === "search" ? "知识检索" : "文档库"}
          </span>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link href="/workspace/chats/new">
            <MessageSquareText className="size-4" />
            新建问答
          </Link>
        </Button>
      </header>
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-8 sm:py-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-muted-foreground mb-2 flex items-center gap-2 text-xs">
                <BookOpen className="size-3.5" />
                技术文档中心
              </div>
              <h1 className="text-2xl font-semibold">
                {view === "search" ? "知识检索" : "文档库"}
              </h1>
            </div>
            {view === "documents" && (
              <Button
                className="bg-emerald-700 text-white hover:bg-emerald-800"
                onClick={() => setUploadOpen(true)}
              >
                <Upload className="size-4" />
                上传文档
              </Button>
            )}
          </div>

          <div className="my-6 grid grid-cols-2 gap-x-4 gap-y-4 border-y py-4 sm:grid-cols-4">
            {[
              {
                label: "知识文档",
                value: status.data?.document_count,
                unit: "份",
              },
              {
                label: "检索片段",
                value: status.data?.chunk_count,
                unit: "段",
              },
              {
                label: "已索引文档",
                value: status.data?.indexed_document_count,
                unit: "份",
              },
            ].map((item) => (
              <div key={item.label}>
                <div className="text-muted-foreground mb-1 text-xs">
                  {item.label}
                </div>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-xl font-semibold tabular-nums">
                    {item.value ?? "—"}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {item.unit}
                  </span>
                </div>
              </div>
            ))}
            <div>
              <div className="text-muted-foreground mb-2 text-xs">索引状态</div>
              {status.isPending ? (
                <span className="text-muted-foreground text-xs">读取中…</span>
              ) : status.data ? (
                <IndexBadge state={status.data.state} />
              ) : (
                <span className="text-xs text-amber-700">状态不可用</span>
              )}
            </div>
          </div>
          {status.error && (
            <ErrorState
              error={status.error}
              retry={() => void status.refetch()}
            />
          )}

          <form
            onSubmit={submit}
            className="flex flex-wrap gap-2"
            role="search"
          >
            <div className="relative min-w-0 flex-1 basis-48">
              <Search className="text-muted-foreground pointer-events-none absolute top-3 left-3 size-4" />
              <Input
                aria-label={view === "search" ? "检索知识库" : "筛选文档"}
                placeholder={
                  view === "search"
                    ? "搜索技术问题、接口名称或关键术语"
                    : "按文件名筛选文档"
                }
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={1000}
                className="h-10 rounded-md pl-10"
              />
            </div>
            <Button
              type="submit"
              className="h-10 bg-emerald-700 text-white hover:bg-emerald-800"
            >
              <Search className="size-4" />
              {view === "search" ? "检索" : "筛选"}
            </Button>
            {view === "search" && (
              <Button asChild variant="outline" className="h-10">
                <Link href={knowledgeChatHref(draft.trim() || query)}>
                  <MessageSquareText className="size-4" />
                  带入问答
                </Link>
              </Button>
            )}
          </form>

          <div
            className="mt-4 flex flex-wrap items-center gap-1 border-b pb-4"
            aria-label="文档分类"
          >
            {["", ...categories].map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={category === value}
                onClick={() => {
                  setDraft(query);
                  navigate(query, value);
                }}
                className={cn(
                  "min-h-8 rounded-md px-3 py-1.5 text-xs transition-colors",
                  category === value
                    ? "bg-emerald-50 font-medium text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {value ? categoryLabel(value) : "全部文档"}
              </button>
            ))}
          </div>

          {view === "documents" ? (
            <section className="py-5" aria-label="文档列表">
              <div className="mb-4 flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">
                  全部文件{" "}
                  <span className="text-muted-foreground ml-1 font-normal">
                    {visibleDocuments.length}
                  </span>
                </h2>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={documents.isFetching}
                  onClick={() =>
                    void client.invalidateQueries({ queryKey: queryRoot })
                  }
                >
                  <RefreshCw
                    className={cn(
                      "size-3.5",
                      documents.isFetching && "animate-spin",
                    )}
                  />
                  刷新
                </Button>
              </div>
              {documents.error ? (
                <ErrorState
                  error={documents.error}
                  retry={() => void documents.refetch()}
                />
              ) : documents.isPending ? (
                <Loading />
              ) : !visibleDocuments.length ? (
                <EmptyState title="暂无匹配文档" icon={FolderOpen} />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[630px] text-left text-sm">
                    <thead className="text-muted-foreground border-b text-xs">
                      <tr>
                        <th className="pb-3 font-normal">文档名称</th>
                        <th className="px-3 pb-3 font-normal">分类</th>
                        <th className="px-3 pb-3 font-normal">索引</th>
                        <th className="px-3 pb-3 text-right font-normal">
                          片段
                        </th>
                        <th className="px-3 pb-3 font-normal">更新日期</th>
                        <th className="pb-3 text-right font-normal">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleDocuments.map((document) => (
                        <tr
                          key={document.path}
                          className="border-b last:border-0"
                        >
                          <td className="max-w-72 py-4 pr-4">
                            <div className="flex items-center gap-3">
                              <FileText className="text-muted-foreground size-4 shrink-0" />
                              <div className="min-w-0">
                                <div className="font-medium break-words">
                                  {document.filename}
                                </div>
                                <div className="text-muted-foreground mt-1 text-xs">
                                  {document.file_type.toUpperCase()} ·{" "}
                                  {formatDocumentSize(document.size)}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-4 text-xs">
                            {categoryLabel(document.category)}
                          </td>
                          <td className="px-3 py-4">
                            <IndexBadge state={document.index_status} />
                          </td>
                          <td className="px-3 py-4 text-right text-xs tabular-nums">
                            {document.chunk_count}
                          </td>
                          <td className="text-muted-foreground px-3 py-4 text-xs whitespace-nowrap">
                            {new Date(document.modified_at).toLocaleDateString(
                              "zh-CN",
                            )}
                          </td>
                          <td className="py-4 text-right whitespace-nowrap">
                            <Button
                              size="icon"
                              variant="ghost"
                              aria-label={`查看 ${document.filename} 的版本`}
                              title="版本记录"
                              onClick={() => setVersionDocument(document)}
                            >
                              <History className="size-4" />
                            </Button>
                            <Button
                              size="icon"
                              variant="ghost"
                              aria-label={`删除 ${document.filename}`}
                              title="删除文档"
                              onClick={() => setDeleteDocument(document)}
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          ) : (
            <div className="grid gap-8 pt-6 lg:grid-cols-[minmax(0,1fr)_240px]">
              <section
                className="min-w-0"
                aria-label="检索结果"
                aria-live="polite"
                aria-busy={results.isFetching}
              >
                <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold">
                    {query ? "检索结果" : "文档概览"}
                  </h2>
                  {query && results.data && (
                    <span className="text-muted-foreground text-xs">
                      {results.data.hits.length} 条候选片段 · 检索耗时{" "}
                      {results.data.elapsed_ms.toFixed(0)} ms
                    </span>
                  )}
                </div>
                {query ? (
                  results.isFetching ? (
                    <Loading />
                  ) : results.error ? (
                    <ErrorState
                      error={results.error}
                      retry={() => void results.refetch()}
                    />
                  ) : results.data?.hits.length ? (
                    <div className="divide-y">
                      {results.data.hits.map((hit, index) => (
                        <article key={hit.chunk_id} className="py-5 first:pt-0">
                          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                            <span className="text-muted-foreground font-mono">
                              {String(index + 1).padStart(2, "0")}
                            </span>
                            <span className="text-muted-foreground">
                              {categoryLabel(hit.category)}
                            </span>
                            {hit.weak_evidence && (
                              <span className="text-amber-700 dark:text-amber-400">
                                证据较弱
                              </span>
                            )}
                          </div>
                          <button
                            type="button"
                            className="text-left text-base font-medium break-words hover:text-emerald-700"
                            onClick={() => setSelectedHit(hit)}
                          >
                            {hit.doc_title || hit.source_file}
                          </button>
                          {hit.section_path && (
                            <div className="text-muted-foreground mt-1 text-xs break-words">
                              {hit.section_path}
                            </div>
                          )}
                          <p className="text-muted-foreground mt-3 line-clamp-3 text-sm leading-7 break-words whitespace-pre-wrap">
                            {hit.text}
                          </p>
                          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                            <button
                              type="button"
                              onClick={() => setSelectedHit(hit)}
                              className="inline-flex items-center gap-1 text-xs text-emerald-700 hover:underline dark:text-emerald-400"
                            >
                              <FileText className="size-3.5" />
                              查看原文片段
                            </button>
                            <Link
                              href={knowledgeChatHref(query)}
                              className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
                            >
                              <MessageSquareText className="size-3.5" />
                              带入问答
                              <ArrowRight className="size-3" />
                            </Link>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="未找到匹配片段" icon={Search} />
                  )
                ) : documents.error ? (
                  <ErrorState
                    error={documents.error}
                    retry={() => void documents.refetch()}
                  />
                ) : documents.isPending ? (
                  <Loading />
                ) : !visibleDocuments.length ? (
                  <EmptyState title="该分类暂无文档" icon={FolderOpen} />
                ) : (
                  <div className="divide-y">
                    {categories
                      .filter((value) => !category || value === category)
                      .map((value) => {
                        const items = (documents.data ?? []).filter(
                          (document) => document.category === value,
                        );
                        if (!items.length) return null;
                        return (
                          <div key={value} className="py-4 first:pt-0">
                            <div className="mb-3 flex items-center justify-between">
                              <h3 className="flex items-center gap-2 text-sm font-medium">
                                <FolderOpen className="size-4 text-emerald-700" />
                                {categoryLabel(value)}
                              </h3>
                              <span className="text-muted-foreground text-xs">
                                {items.length} 份文档
                              </span>
                            </div>
                            <div className="flex flex-col gap-2">
                              {items.map((document) => (
                                <Link
                                  key={document.path}
                                  href={`/workspace/knowledge/documents?category=${encodeURIComponent(value)}`}
                                  className="text-muted-foreground hover:text-foreground flex min-w-0 items-center gap-2 py-1 text-sm"
                                >
                                  <FileText className="size-3.5 shrink-0" />
                                  <span className="min-w-0 break-words">
                                    {document.filename}
                                  </span>
                                  <ChevronRight className="ml-auto size-3.5 shrink-0" />
                                </Link>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    {documents.data?.length === 0 && (
                      <EmptyState title="知识库暂无文档" icon={FolderOpen} />
                    )}
                  </div>
                )}
              </section>
              <aside className="min-w-0 space-y-8 border-t pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6">
                <section>
                  <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                    <MessageSquareText className="size-4" />
                    常见技术问题
                  </h2>
                  <div className="divide-y">
                    {KNOWLEDGE_QUESTIONS.map((question) => (
                      <button
                        type="button"
                        key={question}
                        onClick={() => {
                          setDraft(question);
                          navigate(question);
                        }}
                        className="group text-muted-foreground hover:text-foreground flex w-full items-start gap-2 py-3 text-left text-xs leading-6"
                      >
                        <span className="min-w-0 flex-1">{question}</span>
                        <ArrowRight className="mt-1.5 size-3 shrink-0 group-hover:text-emerald-700" />
                      </button>
                    ))}
                  </div>
                </section>
                <section className="border-t pt-5">
                  <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                    <Database className="size-4" />
                    当前索引
                  </h2>
                  <dl className="space-y-3 text-xs">
                    <div>
                      <dt className="text-muted-foreground mb-1">嵌入后端</dt>
                      <dd className="leading-5 break-all">
                        {status.data?.embedding_backend ?? "—"}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted-foreground">向量维度</dt>
                      <dd>{status.data?.embedding_dim ?? "—"}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground mb-1">
                        索引生成时间
                      </dt>
                      <dd>
                        {status.data?.index_created_at
                          ? new Date(
                              status.data.index_created_at,
                            ).toLocaleString("zh-CN")
                          : "—"}
                      </dd>
                    </div>
                  </dl>
                  <Link
                    href="/workspace/knowledge/documents"
                    className="mt-4 inline-flex items-center gap-1 text-xs text-emerald-700 hover:underline dark:text-emerald-400"
                  >
                    管理文档
                    <ArrowRight className="size-3" />
                  </Link>
                </section>
              </aside>
            </div>
          )}
        </div>
      </main>

      <Dialog
        open={!!selectedHit}
        onOpenChange={(open) => {
          if (!open) setSelectedHit(null);
        }}
      >
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="pr-4 leading-7 break-words">
              {selectedHit?.doc_title}
            </DialogTitle>
            <DialogDescription className="break-all">
              {selectedHit?.source_file}
              {selectedHit?.page_number
                ? ` · 第 ${selectedHit.page_number} 页`
                : ""}
              {selectedHit?.slide_number
                ? ` · 第 ${selectedHit.slide_number} 张幻灯片`
                : ""}
            </DialogDescription>
          </DialogHeader>
          {selectedHit?.weak_evidence && (
            <div className="text-sm text-amber-700">
              该片段证据较弱，请核对后使用。
            </div>
          )}
          <div className="text-sm leading-7 break-words whitespace-pre-wrap">
            {[
              selectedHit?.context_text,
              selectedHit?.parent_excerpt,
              selectedHit?.text,
            ].find((text) => text?.trim())}
          </div>
          <DialogFooter>
            <Button asChild>
              <Link href={knowledgeChatHref(query)}>
                <MessageSquareText className="size-4" />
                带入问答
              </Link>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={uploadOpen}
        onOpenChange={(open) => {
          if (!mutation.isPending) {
            setUploadOpen(open);
            if (!open) setUploadFile(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>上传知识文档</DialogTitle>
            <DialogDescription>
              PDF、PPTX、DOCX、Markdown · 单文件最大 10 MB
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (uploadFile)
                mutation.mutate(() =>
                  uploadKnowledgeDocument(uploadFile, uploadCategory),
                );
            }}
            className="space-y-5"
          >
            <div className="space-y-2">
              <label htmlFor="kb-category" className="text-sm font-medium">
                文档分类
              </label>
              <select
                id="kb-category"
                value={uploadCategory}
                disabled={mutation.isPending}
                onChange={(event) => setUploadCategory(event.target.value)}
                className="border-input bg-background h-10 w-full rounded-md border px-3 text-sm"
              >
                {categories.map((value) => (
                  <option value={value} key={value}>
                    {categoryLabel(value)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <label htmlFor="kb-file" className="text-sm font-medium">
                文件
              </label>
              <input
                ref={fileInput}
                id="kb-file"
                type="file"
                accept=".md,.pdf,.pptx,.docx"
                disabled={mutation.isPending}
                className="block w-full min-w-0 text-sm file:mr-3 file:rounded-md file:border file:bg-transparent file:px-3 file:py-2"
                onChange={(event) => {
                  const file = event.target.files?.[0] ?? null;
                  if (file && file.size > 10 * 1024 * 1024) {
                    toast.error("文件超过 10 MB 上限");
                    event.target.value = "";
                    setUploadFile(null);
                    return;
                  }
                  setUploadFile(file);
                }}
              />
            </div>
            {uploadFile && (
              <div className="text-muted-foreground flex min-w-0 items-center gap-2 text-xs">
                <FileText className="size-4 shrink-0" />
                <span className="min-w-0 flex-1 break-all">
                  {uploadFile.name} · {formatDocumentSize(uploadFile.size)}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={mutation.isPending}
                  aria-label="移除待上传文件"
                  onClick={() => {
                    setUploadFile(null);
                    if (fileInput.current) fileInput.current.value = "";
                  }}
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            )}
            <DialogFooter>
              <Button
                type="submit"
                disabled={!uploadFile || mutation.isPending}
              >
                {mutation.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Upload className="size-4" />
                )}
                {mutation.isPending ? "解析并建立索引…" : "上传并入库"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!versionDocument}
        onOpenChange={(open) => {
          if (!open && !mutation.isPending) setVersionDocument(null);
        }}
      >
        <DialogContent className="max-h-[85dvh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>版本记录</DialogTitle>
            <DialogDescription className="break-all">
              {versionDocument?.path}
            </DialogDescription>
          </DialogHeader>
          {versions.isPending ? (
            <Loading />
          ) : versions.error ? (
            <ErrorState
              error={versions.error}
              retry={() => void versions.refetch()}
            />
          ) : versions.data?.length ? (
            <div className="divide-y">
              {versions.data.map((version) => (
                <div
                  key={version.version_id}
                  className="flex items-center gap-3 py-3"
                >
                  <History className="text-muted-foreground size-4 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm">
                      {new Date(version.created_at).toLocaleString("zh-CN")}
                    </div>
                    <div className="text-muted-foreground mt-1 text-xs break-all">
                      {version.action} · {formatDocumentSize(version.size)} ·{" "}
                      {version.version_id.slice(0, 8)}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={mutation.isPending}
                    onClick={() => {
                      if (versionDocument)
                        setRestoreTarget({
                          document: versionDocument,
                          version,
                        });
                    }}
                  >
                    <RefreshCw className="size-3.5" />
                    恢复
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="暂无历史版本" icon={History} />
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!restoreTarget}
        onOpenChange={(open) => {
          if (!open && !mutation.isPending) setRestoreTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>恢复历史版本？</DialogTitle>
            <DialogDescription className="break-all">
              {restoreTarget?.document.filename}{" "}
              将替换为所选版本并重新建立索引，已保存的历史版本不受影响。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => setRestoreTarget(null)}
            >
              取消
            </Button>
            <Button
              disabled={mutation.isPending}
              onClick={() => {
                if (restoreTarget)
                  mutation.mutate(() =>
                    restoreKnowledgeVersion(
                      restoreTarget.document,
                      restoreTarget.version.version_id,
                    ),
                  );
              }}
            >
              {mutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCw className="size-4" />
              )}
              确认恢复
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={!!deleteDocument}
        onOpenChange={(open) => {
          if (!open && !mutation.isPending) setDeleteDocument(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除文档？</DialogTitle>
            <DialogDescription className="break-all">
              {deleteDocument?.filename}{" "}
              将从知识库和索引中移除，历史版本会保留。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={mutation.isPending}
              onClick={() => setDeleteDocument(null)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              disabled={mutation.isPending}
              onClick={() => {
                if (deleteDocument)
                  mutation.mutate(() =>
                    deleteKnowledgeDocument(deleteDocument),
                  );
              }}
            >
              {mutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Loading() {
  return (
    <div
      role="status"
      className="text-muted-foreground flex items-center gap-2 py-10 text-sm"
    >
      <Loader2 className="size-4 animate-spin" />
      加载中…
    </div>
  );
}

function EmptyState({
  title,
  icon: Icon,
}: {
  title: string;
  icon: LucideIcon;
}) {
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-3 py-12 text-sm">
      <Icon className="size-7 stroke-1" />
      <p>{title}</p>
    </div>
  );
}
