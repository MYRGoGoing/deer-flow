---
title: 知识库语料说明
category: readme
source: 内部说明
---

# 知识库语料说明

本目录是知识库搜索助手的演示语料，内容依据趣链科技（Hyperchain）公开技术资料整理简化而成，仅用于检索功能验证、评测集构建与面试展示，不作为权威技术文档使用。

## 目录结构

- `platform/`：底层平台概述、架构、共识算法、密码学支持
- `contract-dev/`：智能合约开发（HVM、EVM 兼容、Gas 计费）
- `baas/`：BaaS 平台与部署方式
- `crosschain/`：跨链平台 BitXHub
- `api-reference/`：JSON-RPC 接口基础

## 支持的文件格式

- Markdown：解析 frontmatter、标题和正文。
- PDF：按页提取文本和表格；启用视觉模型后，对无文本层的扫描页执行 OCR/视觉描述。
- PPTX：按幻灯片提取文本和表格；启用视觉模型后，提取内嵌图片中的文字、表格和图示关系。
- DOCX：转为 Markdown；启用视觉模型后，提取文档媒体包中的图片内容。

表格、OCR 和图片描述会分别以 `table`、`ocr`、`image` 内容类型入库，并保留原文件、页码或幻灯片号用于回答引用。当前视觉链路先把图片转换为结构化文本，再复用文本 Embedding 和混合检索；尚未实现原始图片向量的跨模态检索。

## Markdown 格式约定

每篇文档头部使用 frontmatter 声明元数据：

```text
---
title: 文档标题
category: 目录分类名
source: 来源说明
---
```

替换为真实企业语料时，把支持的文件放入对应业务分类目录，重新执行入库命令即可重建索引。视觉解析默认关闭；只有显式配置 `KB_VISION_BACKEND=openai`、`KB_VISION_MODEL` 和 `KB_VISION_API_KEY` 后才会调用外部视觉模型。

## 知识库管理接口

Gateway 提供 `/api/kb` 管理接口，读写权限彼此独立：

- `GET /api/kb/status`：查看语料与索引是否一致，以及文档、分块和 Embedding 元数据。
- `GET /api/kb/documents`：查看文档清单、内容哈希、分块数和 `indexed/stale/missing` 状态。
- `POST /api/kb/upload`：上传并增量更新索引，要求 `kb:write`。
- `DELETE /api/kb/documents/{category}/{filename}`：删除文档和索引内容，同时保留可恢复快照。
- `GET /api/kb/documents/{category}/{filename}/versions`：查看不可变版本历史。
- `POST /api/kb/documents/{category}/{filename}/versions/{version_id}/restore`：恢复指定版本并重新入库。
- `GET /api/kb/audit`：查看上传、删除和恢复审计事件，要求 `kb:write`。

每次成功写操作都会在 `KB_MANAGEMENT_DIR` 保存内容快照、SHA-256、操作者和时间。Gateway 多 Worker 通过文件锁串行化语料与索引更新；该方式适合单机部署，跨主机部署应把版本与审计迁移到数据库/对象存储，并改用分布式锁或消息队列。

启用 DeerFlow RBAC 后，可在 `authorization.provider.config.roles.*.routes` 中分别配置 `kb:read` 与 `kb:write`。鉴权总开关关闭时沿用本地开发兼容行为，登录用户拥有全部路由权限。
