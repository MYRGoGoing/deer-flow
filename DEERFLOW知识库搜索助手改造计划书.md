# DeerFlow 知识库搜索助手改造计划书

> 更新日期：2026-09-16  
> 项目目录：`/Users/mengyangran/简历/简历项目学习/deer-flow_two`  
> 目标：把 DeerFlow 2.0 从通用 Agent 框架改造成可演示、可评测、可维护的企业技术文档知识库助手。

## 1. 目标和边界

### 1.1 业务目标

面向企业技术手册、产品介绍、接口说明、合约开发和运维资料分散的问题，提供：

- 多格式文档统一入库。
- 自然语言和专有术语混合检索。
- 仅基于知识库证据回答，并提供数字引用。
- 证据不足时拒答。
- 文档可增量更新、删除、恢复和审计。
- 通过黄金集持续评测，避免只靠人工演示判断效果。

### 1.2 当前真实范围

- 语料：10 篇公开资料整理的 Markdown 文档。
- 索引：53 个 Chunk，本地 BGE 512 维向量 + BM25 文件索引。
- 黄金集：60 条，50 条可答、10 条越界。
- 已实现格式：Markdown、PDF、PPTX、DOCX；包含页码、幻灯片、表格和视觉/OCR 分支。
- 当前部署：单机、本地文件索引和本地 ONNX Embedding，不是 Milvus/ES 集群。
- 当前端到端生成模型：`deepseek-v4-pro`；独立 Judge 未启用。

### 1.3 上游和自研边界

DeerFlow 上游提供 Gateway、Run/Worker、LangGraph、Tool/Skill 扩展、事件流和状态运行时。本次改造的主要自研范围是文档解析、分块、Embedding/BM25/RRF 检索、证据门控、知识库 Tool/Skill、评测、文档管理、版本审计和数字引用前端体验。

## 2. 总体架构

```text
文档目录 / 上传 API
      |
      v
解析器 -> 统一 SourceSection -> Parent-Child Chunker
      |                              |
      |                              +-> 页码/幻灯片/表格/内容哈希
      v
BGE 向量索引 + BM25 倒排索引
      |
      v
Dense/BM25 召回 -> RRF -> 证据门控 -> Parent/相邻章节扩展
      |
      v
DeerFlow Agent: Model -> kb_search Tool -> ToolMessage -> Model
      |
      v
带数字引用的答案 -> SSE 流式展示 -> 来源聚合与回查
      |
      +-> 版本/权限/审计/一致性
      +-> 黄金集检索与端到端评测
```

## 3. 八阶段实施记录

### 第一阶段：冻结当前 baseline，统一配置和评测

状态：**已完成**

- 固定知识库目录、索引目录、Chunk 参数和阈值环境变量。
- 建立 60 条黄金集，区分可答与越界问题。
- 评测报告绑定黄金集哈希、语料哈希、索引后端和模型配置。
- 支持检索报告与端到端 checkpoint 断点续跑。
- 当前真实结果见 `evals/kb_qa/baselines/local-bge-small-zh/`。

验收结果：

| 配置 | Recall@5 | Recall@10 | Precision@5 | P50/P95 |
|---|---:|---:|---:|---:|
| BGE Dense | 92% | 96% | 42.0% | 3.94/4.48ms |
| BM25 | 100% | 100% | 44.0% | 0.12/0.18ms |
| BGE + BM25 + RRF | 98% | 100% | 42.8% | 12.66/14.18ms |

### 第二阶段：接入真实 Embedding

状态：**已完成**

- 接入本地 `BAAI/bge-small-zh-v1.5` ONNX 服务。
- 通过 OpenAI-compatible 接口调用，避免把密钥写入代码。
- 固定 512 维索引元数据，后端发现 Embedding 配置与索引不一致时拒绝检索并提示重建。
- `make kb-start` 自动启动本地模型服务，限制 ONNX 线程数为 2。

### 第三阶段：增加 Reranker 和消融实验

状态：**已完成，结论是默认关闭**

通用 MultiBERT Reranker 在当前中文技术语料上产生负收益：Recall@5 从 RRF 的 98% 降到 92%，Precision@5 从 42.8% 降到 37.6%，P95 接近 940ms。因此保留可插拔接口和评测脚本，但演示配置不启用，不把 Reranker 写成效果提升点。

### 第四阶段：支持 PDF/PPT/Word 文档解析

状态：**已完成代码和文件级测试**

- PDF 按页解析文本和表格。
- PPTX 按幻灯片解析文本、表格和图片内容。
- DOCX 按标题、段落和表格解析。
- 所有格式转为统一的来源章节结构，再复用同一套分块、索引和引用链路。
- 保留页码、幻灯片号、表格类型和文件类型元数据。

边界：已完成管道和测试，正式黄金集仍主要是 Markdown，不写生产级文档规模。

### 第五阶段：接入图片、表格和 OCR 内容

状态：**已完成可配置视觉/OCR 管道，未完成跨模态评测**

- 表格转为带 `content_type=table` 的 Markdown 文本。
- PDF 扫描页和 PPT 图片可经过视觉模型转为结构化文本。
- 设置图片大小、DPI、超时、重试和响应校验。
- 没有配置视觉模型时不发起外部请求。

真实表达：当前是“视觉转文本后进入文本 RAG”，不是图片与文字统一向量空间；尚无图文黄金集，因此不能写 OCR 准确率或跨模态 Recall。

### 第六阶段：补充端到端 RAG 评测

状态：**已完成固定生成模型回归，Judge 指标待配置**

当前报告：`evals/kb_qa/baselines/local-bge-small-zh/e2e-production-report.md`

| 指标 | 结果 |
|---|---:|
| Refusal Accuracy | 100% |
| Keyword Recall | 93% |
| Reference-answer Token F1 | 38.8% |
| Citation Validity | 100% |
| Expected-source Citation Rate | 100% |
| P50/P95 | 4596/12807ms |
| Faithfulness/Answer Relevancy | N/A，未启用独立 Judge |

注意：Keyword Recall 和 Token F1 是确定性词法诊断，不等于问答准确率；没有 Judge 就不宣称 Faithfulness 或 Answer Relevancy。

### 第七阶段：完善知识库管理、版本、权限和引用

状态：**已完成核心闭环**

- 增加状态、文档列表、上传、删除、版本列表、恢复和审计 API。
- 读写权限拆分为 `kb:read` 与 `kb:write`。
- 上传限制分类、文件名、格式、UTF-8 Markdown 和文件大小。
- 临时文件 `fsync` 后通过 `os.replace` 原子替换。
- 索引失败时恢复旧文档和旧索引。
- 版本快照保存 SHA-256、操作者、时间、动作和恢复来源。
- 使用跨进程文件锁协调单机多 Worker 写操作。
- 语料 manifest 和索引 manifest 用于判断 `ready/stale/missing`。
- 前端把 `[1]`、`[2]` 渲染成数字引用，并聚合显示来源。
- 兼容模型输出的 Markdown 列表引用：`- [1]`、`* [1]`、`+ [1]`。

### 第八阶段：根据真实完成结果更新简历和手册

状态：**已完成第一版定稿**

已更新：

- `DEERFLOW企业知识库Agent五条简历亮点与面试准备手册.md`
- `DEERFLOW简历项目描述与面试学习顺序.md`
- 本计划书

原始文件 `DEERFLOW前五条简历亮点深度准备与面试拷打手册.md` 保持不动。

## 4. 运行、测试和演示流程

### 4.1 日常启动

```bash
cd /Users/mengyangran/简历/简历项目学习/deer-flow_two
make kb-start
```

访问 `http://localhost:2026`。停止：

```bash
make stop
```

轻量模式使用预构建前端、本地 BGE、2 个线程和已评测索引。`make dev` 会启用前后端热更新、文件监听和重新编译，适合开发修改，不适合日常演示，尤其在 16GB 机器上更容易出现启动慢、页面慢和系统卡顿。

### 4.2 文档增量更新

把文件放入 `data/knowledge_base/<category>/` 后执行：

```bash
cd backend
PYTHONPATH=packages/harness:. uv run python -m deerflow.community.kb_search.ingest \
  --doc ../data/knowledge_base/platform/your-document.md
```

删除索引中的单篇文档：

```bash
PYTHONPATH=packages/harness:. uv run python -m deerflow.community.kb_search.ingest \
  --remove ../data/knowledge_base/platform/your-document.md
```

通过管理 API 上传、删除和恢复时会写版本和审计；CLI 更适合本地开发调试。全量本地评测：

```bash
./scripts/kb_local_eval.sh
```

复制项目后不要跨目录复用 `.venv` 或 `node_modules`。`.venv/bin/pytest` 的 shebang 可能仍指向原项目，应使用 `PYTHONPATH=packages/harness:. uv run python -m pytest ...`。

### 4.3 建议验收问题

```text
HVM 如何声明合约入口和可调用方法？请给出数字引用和参考来源。
RBFT 共识的基本流程是什么？
BaaS 有哪些部署模式？
HVM 与 EVM 在开发语言和兼容性上有什么区别？
@Contract 和 @Transaction 分别有什么作用？
公司的年假审批流程是什么？
```

检查四件事：是否调用知识库 Tool、是否有数字引用、来源是否能展开、越界问题是否拒答。

## 5. 测试与验收记录

已完成的验证包括：

- 本轮后端知识库 focused tests：56 passed；此前扩展鉴权回归也已完成。
- 本轮前端全量测试：993 passed；ESLint、Prettier、TypeScript 和生产构建验证通过。
- 生产构建生成 100 个静态页面。
- 真实 UI HVM 问答：Agent 调用 `kb_search`，Run 最终为 `success`，约 22 秒，来源面板显示 3 个来源。
- 服务端口：Embedding `18080`、Gateway `8001`、Frontend `3000`、Nginx `2026`。
- `make stop` 后已确认四个端口无残留监听进程。

## 6. 风险和后续生产化

当前版本已经是“可运行、可评测、可维护”的本地业务闭环，但还不是大规模生产系统。后续应：

1. 使用脱敏真实企业资料扩展语料和独立测试集。
2. 收集真实搜索日志，加入错别字、缩写、口语和多轮问题。
3. 启用独立 Judge，配合人工抽检评估 Faithfulness 和 Answer Relevancy。
4. 为图文资料建立专门黄金集，再决定多模态 Embedding。
5. 将原文和版本迁移到对象存储，将元数据和审计迁移到数据库。
6. 使用 Milvus/pgvector/Elasticsearch 等后端替换文件索引，并做容量压测。
7. 将单机文件锁升级为任务表、数据库锁或 Redis 分布式锁。
8. 增加部门/文档级 ACL、监控告警、失败重试和异步入库任务。

## 7. 计划完成标准

当用户能够：

- 从文档上传讲到引用答案。
- 用指标解释检索和生成质量。
- 演示可答问题、越界拒答和文档更新。
- 说明权限、版本、回滚和审计如何工作。
- 分清 DeerFlow 上游能力与本次改造。
- 主动说明单机、小语料、未启用 Judge 和未完成图文黄金集的边界。

就完成了本计划第一轮闭环。之后的重点从“继续堆功能”转为真实资料扩充、错误分析和面试表达训练。
