# Knowledge Base Retrieval Eval

- Generated at: `2026-09-15T17:47:04`
- Golden set: `60` questions (`50` answerable, `10` unanswerable)
- Index directory: `/Users/mengyangran/简历/简历项目学习/deer-flow_two/data/kb_index_local_bge`

| Config | Recall@5 | Recall@10 | Precision@5 | Precision@10 | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|
| dense | 46/50 (92.0%) | 48/50 (96.0%) | 42.0% | 28.2% | 3.94 | 4.48 |
| bm25 | 50/50 (100.0%) | 50/50 (100.0%) | 44.0% | 28.4% | 0.12 | 0.18 |
| hybrid_rrf | 49/50 (98.0%) | 50/50 (100.0%) | 42.8% | 30.4% | 12.66 | 14.18 |

## Evidence gate

Answerable retention: **50/50 (100.0%)**.
Refusal correctness: **10/10 (100.0%)**.
Overall gate accuracy: **60/60 (100.0%)**.

## Recall by category

| Category | Count | Dense@5 | RRF@5 | Dense@10 | RRF@10 |
|---|---:|---:|---:|---:|---:|
| api-reference | 5 | 100% | 100% | 100% | 100% |
| baas | 5 | 100% | 100% | 100% | 100% |
| contract-dev | 15 | 93% | 100% | 93% | 100% |
| crosschain | 5 | 100% | 100% | 100% | 100% |
| platform | 20 | 85% | 95% | 95% | 100% |
| unanswerable | 10 | 0% | 0% | 0% | 0% |

## Evidence-gate failures

False refusals: None.

## Hybrid RRF misses

- `overview-003` 平台支持哪两种智能合约引擎？ -> expected `platform/platform-overview.md`
