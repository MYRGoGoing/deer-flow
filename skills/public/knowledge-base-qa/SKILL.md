---
name: knowledge-base-qa
description: Use this skill for ANY question about 趣链科技/Hyperchain products, BaaS deployment, smart contracts (HVM/EVM), RBFT consensus, BitXHub cross-chain, JSON-RPC APIs or other internal documentation topics. Trigger on company/product/domain questions. Enforces systematic knowledge-base retrieval with mandatory citations and refusal when evidence is missing.
---

# Knowledge Base QA Skill

## When to Use This Skill

Load this skill whenever the user asks about Hyperchain platform capabilities, deployment, consensus, cryptography, smart contract development, cross-chain features or API usage. These questions MUST be answered from `kb_search` evidence, never from model memory alone.

## Core Principles

1. **检索优先**：先调 `kb_search`，再回答。模型记忆只能用来组织语言，不能提供事实。
2. **强制引用**：回答中的每个事实性结论标注 `[编号]`，编号对应检索结果里的 index。没有引用支撑的结论不得写入回答。
3. **证据不足必须拒答**：当 `total_results` 为 0，或所有结果都标记 `weak_evidence: true` 时，回复"知识库中暂无相关内容"，禁止编造或用通用知识顶替。

## Workflow

1. **首轮检索**：把用户问题改写为检索友好的关键词组合，调用 `kb_search`。
2. **覆盖度评估**：检查返回结果是否足以回答问题。不足时进行改写重试，最多 3 轮：
   - 同义替换（如"部署方式"→"SaaS 托管 私有化 混合云"）
   - 中英文互换（如"跨链"→"BitXHub IBTP"）
   - 上下位词扩展（如"gas 怎么算"→"gas 计费模式 gasPrice gasLimit"）
3. **限定范围**：能判断所属目录时传 `category` 参数缩小范围（platform / contract-dev / baas / crosschain / api-reference）。
4. **多跳问题拆解**：对比类、流程类复杂问题拆成多个子查询分别检索，再综合作答，每个子结论分别引用。

## Answer Format

```text
（直接回答问题的一句话总结）

- 要点一……[1]
- 要点二……[2][3]

参考来源：
[1] 文档标题 | 章节 | 来源链接
```

弱证据（`weak_evidence: true`）的片段只能作为背景提及，并明确说明把握有限；绝不能基于弱证据下确定性结论。
