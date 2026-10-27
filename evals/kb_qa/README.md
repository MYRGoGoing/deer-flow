# Knowledge Base Evaluation

本目录包含知识库的两层评测，所有指标都绑定黄金集哈希、语料哈希、索引后端和运行配置，避免不同版本结果混用。

## 1. 检索与证据门控评测

零 Key 的本地 baseline：

```bash
./scripts/kb_baseline.sh
```

报告比较 Dense、BM25、Hybrid RRF，以及启用 Reranker 后的重排结果，统计 Recall@K、Precision@K、延迟和证据门控拒答率。

## 2. 端到端 RAG 评测

先在 `.env` 配置 OpenAI-compatible 生成模型：

```bash
export KB_E2E_BASE_URL=https://api.siliconflow.cn/v1
export KB_E2E_MODEL=your-answer-generation-model
export KB_E2E_API_KEY=your-api-key
```

运行 60 条完整评测：

```bash
backend/.venv/bin/python evals/kb_qa/run_e2e_eval.py
```

先跑 3 条冒烟测试：

```bash
backend/.venv/bin/python evals/kb_qa/run_e2e_eval.py --limit 3 --fresh --no-judge
```

配置 `KB_E2E_JUDGE_MODEL` 后，会增加独立 LLM Judge 的 Faithfulness 与 Answer Relevancy。建议 Judge 与生成模型使用不同模型，减少自评偏差。

默认每完成一条样本都会原子更新 `e2e-checkpoint.json`，中途失败后再次执行会从断点继续；语料、索引、模型或样本范围变化时，使用 `--fresh` 开始新实验。

## 指标边界

- `Keyword Recall`：答案覆盖黄金关键词的比例，是可复现词法诊断，不等于语义正确率。
- `Reference-answer token F1`：生成答案与参考答案的分词重合度，不适合单独判断开放式回答质量。
- `Citation Validity`：回答引用编号是否落在本次检索结果范围内。
- `Expected-source citation rate`：至少一个合法引用是否指向黄金来源文档。
- `Refusal Accuracy`：可答问题未误拒答、越界问题正确拒答的总体比例。
- `Faithfulness`：LLM Judge 判断回答事实是否有检索证据支持。
- `Answer Relevancy`：LLM Judge 判断回答是否直接解决用户问题。

没有真实生成模型或 Judge 的运行报告时，简历中不能填写端到端准确率、Faithfulness 或 Answer Relevancy。
