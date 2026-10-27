import { KnowledgeWorkspace } from "@/components/workspace/knowledge/knowledge-workspace";

export const metadata = { title: "文档库 · 企业知识库" };

export default function KnowledgeDocumentsPage() {
  return <KnowledgeWorkspace view="documents" />;
}
