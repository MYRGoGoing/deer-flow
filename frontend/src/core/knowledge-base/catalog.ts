export const KNOWLEDGE_CATEGORIES = [
  { value: "platform", label: "平台与共识" },
  { value: "contract-dev", label: "智能合约" },
  { value: "baas", label: "部署与运维" },
  { value: "crosschain", label: "跨链协作" },
  { value: "api-reference", label: "接口参考" },
] as const;

export const KNOWLEDGE_QUESTIONS = [
  "RBFT 共识如何保证交易的一致性？",
  "HVM 与 EVM 在合约开发上有什么区别？",
  "BaaS 平台有哪些部署模式？",
  "如何通过 JSON-RPC 查询交易回执？",
];

export function categoryLabel(value: string) {
  return (
    KNOWLEDGE_CATEGORIES.find((item) => item.value === value)?.label ?? value
  );
}

export function knowledgeChatHref(question: string) {
  return `/workspace/chats/new?question=${encodeURIComponent(question)}`;
}

export function formatDocumentSize(bytes: number) {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}
