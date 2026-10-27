# DeerFlow 企业知识库项目描述与面试学习顺序

> 更新日期：2026-09-16  
> 本文用于安排源码学习和面试训练；最终五条简历表述及完整话术以《DEERFLOW企业知识库Agent五条简历亮点与面试准备手册》为准。

## 一、最终项目描述

### 项目名称

**企业技术文档知识库智能助手（DeerFlow 2.0 二次开发）**

### 项目简介

面向企业技术资料分散、专业术语检索困难和大模型回答缺少依据的问题，基于 DeerFlow 2.0 二次开发知识库 Agent，支持 Markdown/PDF/PPTX/DOCX 入库、BGE+BM25+RRF 混合检索、弱证据拒答、数字引用、版本权限审计及流式问答。

### 五条简历亮点

1. **多格式文档解析与结构化入库：** 面向技术手册格式不统一、章节和表格语义易丢失的问题，支持 Markdown/PDF/PPTX/DOCX 解析，采用 Parent-Child 分块保留标题层级、页码、幻灯片及表格元数据，并支持单文档增量索引。

2. **混合检索与效果优化：** 针对自然语言查询与 API、产品名等精确术语并存的场景，构建本地 BGE、BM25 与 RRF 混合检索，结合元数据过滤和相邻上下文扩展兼顾语义与词法召回；60 条黄金集上 Recall@5/10 达 98%/100%，较纯 Dense 提升 6 个百分点，P95 为 14.18ms。

3. **评测驱动与幻觉控制：** 针对弱证据易诱发模型幻觉的问题，建立检索、证据门控和端到端 RAG 分层评测，并通过消融实验关闭对中文技术语料产生负收益的通用 Reranker；证据门控 60/60 判断正确，越界拒答率与引用合法率均达 100%。

4. **Agent 问答与流式执行：** 将知识库检索封装为 Agent Tool/Skill，基于 DeerFlow 的 LangGraph Runtime 执行查询改写、工具调用和证据回答，通过 Worker 与 SSE 增量返回结果；真实 UI 完成长任务问答及数字引用展示。

5. **知识治理与引用闭环：** 面向企业资料持续更新、误删恢复和来源追溯需求，实现文档上传、删除、版本恢复、索引一致性检查及读写权限隔离，结合原子写入、失败回滚、文件锁和审计日志保障文档与索引一致，并在前端聚合展示章节、页码等引用来源。

## 二、推荐学习顺序

不要按文件数量从头读到尾。按照一次真实请求的生命周期学习，先形成业务全景，再下钻算法和工程细节。

### 第 1 阶段：先会演示和说明边界

目标：知道系统解决什么问题，能稳定完成一次成功问答和一次拒答。

操作：

```bash
cd /Users/mengyangran/简历/简历项目学习/deer-flow_two
make kb-start
```

测试：

```text
HVM 如何声明合约入口和可调用方法？请给出数字引用和参考来源。
公司的年假审批流程是什么？
```

完成标准：

- 能指出可答问题调用了 `kb_search`，答案有数字引用和来源面板。
- 能说明越界问题为什么被拒答。
- 能背出真实规模：10 篇文档、53 个 Chunk、60 条黄金集。
- 知道当前是单机文件索引，不是大规模生产集群。

### 第 2 阶段：文档解析和分块

先读：

```text
backend/packages/harness/deerflow/community/kb_search/parsers.py
backend/packages/harness/deerflow/community/kb_search/chunker.py
backend/packages/harness/deerflow/community/kb_search/ingest.py
backend/packages/harness/deerflow/community/kb_search/stores.py
```

需要掌握：

- 四种文件如何转换成统一 `ParsedSource/SourceSection`。
- PDF 页码、PPT 幻灯片、表格和视觉文本如何进入元数据。
- Parent 和 Child 各自承担什么职责。
- 为什么文档路径和内容哈希要稳定。
- 全量重建、单文档 upsert 和 remove 的差异。

练习题：

1. 为什么不直接固定 500 字切块？
2. Parent-Child 如何同时改善精确召回和上下文完整性？
3. 表格转 Markdown 的优点和局限是什么？
4. 当前为什么不能声称是统一图文向量检索？

动手任务：新增一篇 Markdown 文档，执行单文档增量入库，再用新知识点提问验证。

### 第 3 阶段：Embedding、BM25 和 RRF

先读：

```text
backend/packages/harness/deerflow/community/kb_search/embeddings.py
backend/packages/harness/deerflow/community/kb_search/stores.py
backend/packages/harness/deerflow/community/kb_search/retriever.py
backend/packages/harness/deerflow/community/kb_search/reranker.py
scripts/kb_local_model_server.py
```

需要掌握：

- BGE Embedding 如何通过 OpenAI-compatible 本地接口被调用。
- 向量余弦相似度和 BM25 分别擅长什么问题。
- RRF 为什么能融合不同分数空间。
- `top_k`、`fetch_k`、`rrf_k` 和候选数的作用。
- 为什么当前通用 Reranker 被关闭。

必须记住的数字：

```text
Dense Recall@5/10：92%/96%
BM25 Recall@5/10：100%/100%
Hybrid Recall@5/10：98%/100%
Hybrid P95：14.18ms
Reranker：Recall@5 降至 92%，P95 升至约 940ms
```

练习题：

1. 为什么 BM25 在当前集合中比 Dense 更高？
2. BM25 已经很好，保留 Dense 的业务理由是什么？
3. 为什么不直接把两个原始分数加权相加？
4. 如何针对新领域重新选择 Reranker？

### 第 4 阶段：证据门控和评测

先读：

```text
evals/kb_qa/golden_set.json
evals/kb_qa/run_eval.py
evals/kb_qa/run_e2e_eval.py
evals/kb_qa/baselines/local-bge-small-zh/production-report.md
evals/kb_qa/baselines/local-bge-small-zh/e2e-production-report.md
```

需要掌握：

- Recall@K、Precision@K 的计算和业务意义。
- 证据门控如何组合 Dense、BM25、词法覆盖和排名共识。
- 可答保留率与越界拒绝率为什么要分开统计。
- Keyword Recall、Token F1、Citation Validity、Expected-source Citation Rate 的区别。
- 为什么没有 Judge 就不能声称 Faithfulness 或 Answer Relevancy。
- checkpoint、实验签名和语料/黄金集哈希如何避免报告混用。

必须记住的数字：

```text
门控：50/50 可答保留，10/10 越界拒答
端到端：拒答 100%，关键词覆盖 93%，Token F1 38.8%
引用合法 100%，预期来源引用 100%
P50/P95：4596/12807ms
```

练习题：

1. Token F1 为什么不能写成问答准确率？
2. 引用编号合法为什么仍不等于答案忠实？
3. 黄金集如何拆分调优集和测试集？
4. 如何用真实用户日志构建困难样本？

### 第 5 阶段：Tool、Skill、LangGraph 和流式执行

先读知识库改造：

```text
backend/packages/harness/deerflow/community/kb_search/tools.py
skills/public/knowledge-base-qa/SKILL.md
frontend/src/core/citations/numeric-sources.ts
frontend/src/components/workspace/messages/markdown-content.tsx
```

再读 DeerFlow 上游执行链路：

```text
backend/app/gateway/routers/thread_runs.py
backend/packages/harness/deerflow/runtime/runs/manager.py
backend/packages/harness/deerflow/runtime/runs/worker.py
backend/packages/harness/deerflow/agents/lead_agent/agent.py
```

需要掌握：

- Tool 解决能力调用，Skill 解决调用策略。
- `AIMessage.tool_calls -> ToolNode -> ToolMessage -> Model` 闭环。
- Gateway 为什么不在请求函数中同步跑完整 Agent。
- Worker、事件存储和 SSE 如何解耦任务与连接。
- 引用列表为什么要兼容 `- [1]`、`* [1]` 和 `+ [1]`。
- 哪些能力是 DeerFlow 上游，哪些是本次二次开发。

练习题：

1. 一个 HVM 问题从前端到引用面板经历哪些步骤？
2. 只有 Tool，没有 Skill 会出现什么问题？
3. 检索 14ms，为什么 UI 仍可能耗时 22 秒？
4. 浏览器断线后，Run 为什么不一定停止？

### 第 6 阶段：知识库治理

先读：

```text
backend/app/gateway/routers/knowledge_base.py
backend/app/gateway/authz.py
backend/packages/harness/deerflow/community/kb_search/documents.py
backend/packages/harness/deerflow/community/kb_search/management.py
```

需要掌握：

- `kb:read` 和 `kb:write` 的权限边界。
- 临时文件、`fsync`、`os.replace` 和失败回滚的职责。
- 为什么要同时保存原文快照、SHA-256、版本元数据和审计事件。
- manifest 哈希如何判断语料与索引是否同步。
- 文件锁能解决什么，并发到多主机时为什么不够。

练习题：

1. 原子文件替换为什么不等于完整事务？
2. 上传成功但索引失败时如何恢复？
3. 删除与恢复如何保持可审计？
4. 迁移到 Kubernetes 多副本需要替换哪些组件？

## 三、七天面试训练安排

| 天数 | 主题 | 当天输出 |
|---|---|---|
| 第 1 天 | 演示、业务背景、系统架构 | 两分钟项目介绍 + 架构图 |
| 第 2 天 | 多格式解析、分块、增量入库 | 手画数据结构 + 新增一篇文档 |
| 第 3 天 | Dense、BM25、RRF、Reranker | 讲清指标表和消融结论 |
| 第 4 天 | 黄金集、门控、端到端评测 | 手算一组 Recall/Precision |
| 第 5 天 | Tool/Skill、LangGraph、SSE | 画完整请求时序图 |
| 第 6 天 | 权限、版本、回滚、审计 | 讲清一次上传事务 |
| 第 7 天 | 模拟面试 | 连续回答 20 个追问并复盘 |

## 四、演示与开发命令

轻量启动：

```bash
make kb-start
```

停止并回收 `18080/8001/3000/2026`：

```bash
make stop
```

`make dev` 用于修改前后端时的热更新，不用于日常演示。它会启用 Next.js 开发编译、后端 reload 和文件监听，启动与页面响应更慢、资源占用也更高。

复制项目后不要复用另一目录的 `.venv` 或 `node_modules`。运行后端测试时使用：

```bash
cd backend
PYTHONPATH=packages/harness:. uv run python -m pytest ...
```

避免直接执行可能仍带旧目录 shebang 的 `.venv/bin/pytest`。

## 五、最终掌握标准

达到以下标准后，这个项目才真正属于你：

- 不看稿完成两分钟项目串讲，并主动说明真实边界。
- 能从一篇文档画到最终引用答案，解释每个中间产物。
- 能解释全部核心指标，不把词法指标包装成准确率。
- 能回答为什么关闭 Reranker、为什么当前不用 Milvus。
- 能独立增删文档、重建索引、运行评测并定位失败样本。
- 能区分 DeerFlow 上游能力和自己的知识库改造。
- 面对“这只是 Demo 吗”时，能从评测、治理、权限、回滚和业务闭环回答，而不是只罗列技术名词。
