import { KnowledgeWorkspace } from "@/components/workspace/knowledge/knowledge-workspace";

export const metadata = { title: "知识检索 · 企业知识库" };

export default function KnowledgePage() {
  return <KnowledgeWorkspace view="search" />;
}
