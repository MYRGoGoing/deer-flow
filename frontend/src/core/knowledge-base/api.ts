import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export interface KnowledgeStatus {
  state: "ready" | "stale" | "missing";
  in_sync: boolean;
  document_count: number;
  indexed_document_count: number;
  chunk_count: number;
  embedding_backend: string | null;
  embedding_dim: number | null;
  index_created_at: string | null;
}

export interface KnowledgeDocument {
  path: string;
  category: string;
  filename: string;
  file_type: string;
  size: number;
  modified_at: string;
  index_status: "indexed" | "stale" | "missing";
  chunk_count: number;
}

export interface KnowledgeHit {
  chunk_id: string;
  doc_title: string;
  source_file: string;
  category: string;
  text: string;
  section_path: string;
  context_text: string;
  parent_excerpt: string;
  page_number: number | null;
  slide_number: number | null;
  weak_evidence: boolean;
}

export interface KnowledgeSearch {
  query: string;
  hits: KnowledgeHit[];
  elapsed_ms: number;
}

export interface KnowledgeVersion {
  version_id: string;
  created_at: string;
  action: string;
  size: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getBackendBaseURL()}/api/kb${path}`, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      detail?: unknown;
    };
    const detail = typeof body.detail === "string" ? body.detail : undefined;
    throw new Error(
      response.status === 403
        ? "当前账号没有此操作的知识库权限"
        : (detail ?? `知识库请求失败（${response.status}），请稍后重试`),
    );
  }
  return response.json() as Promise<T>;
}

export function getKnowledgeStatus(signal?: AbortSignal) {
  return request<KnowledgeStatus>("/status", { signal });
}

export function getKnowledgeDocuments(signal?: AbortSignal) {
  return request<KnowledgeDocument[]>("/documents", { signal });
}

export function searchKnowledge(
  query: string,
  category: string,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ q: query });
  if (category) params.set("category", category);
  return request<KnowledgeSearch>(`/search?${params}`, { signal });
}

export function uploadKnowledgeDocument(file: File, category: string) {
  const body = new FormData();
  body.set("file", file);
  body.set("category", category);
  return request<{ success: boolean; message: string }>("/upload", {
    method: "POST",
    body,
  });
}

function documentPath(document: KnowledgeDocument) {
  return `/documents/${encodeURIComponent(document.category)}/${encodeURIComponent(document.filename)}`;
}

export function deleteKnowledgeDocument(document: KnowledgeDocument) {
  return request<{ message: string }>(documentPath(document), {
    method: "DELETE",
  });
}

export function getKnowledgeVersions(
  document: KnowledgeDocument,
  signal?: AbortSignal,
) {
  return request<KnowledgeVersion[]>(`${documentPath(document)}/versions`, {
    signal,
  });
}

export function restoreKnowledgeVersion(
  document: KnowledgeDocument,
  versionId: string,
) {
  return request<{ message: string }>(
    `${documentPath(document)}/versions/${encodeURIComponent(versionId)}/restore`,
    { method: "POST" },
  );
}
