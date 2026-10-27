# Knowledge Base Retrieval Eval

- Generated at: `2026-09-15T16:28:19`
- Golden set: `60` questions (`50` answerable, `10` unanswerable)
- Index directory: `/Users/mengyangran/简历/简历项目学习/deer-flow_two/data/kb_index`

| Config | Recall@5 | Recall@10 | Precision@5 | Precision@10 | P50 ms | P95 ms |
|---|---:|---:|---:|---:|---:|---:|
| dense | 48/50 (96.0%) | 49/50 (98.0%) | 38.0% | 25.4% | 0.04 | 0.05 |
| bm25 | 50/50 (100.0%) | 50/50 (100.0%) | 44.0% | 28.4% | 0.08 | 0.11 |
| hybrid_rrf | 48/50 (96.0%) | 50/50 (100.0%) | 42.4% | 27.8% | 0.52 | 0.60 |

## Evidence gate

Answerable retention: **48/50 (96.0%)**.
Refusal correctness: **9/10 (90.0%)**.
Overall gate accuracy: **57/60 (95.0%)**.

## Recall by category

| Category | Count | Dense@5 | RRF@5 | Dense@10 | RRF@10 |
|---|---:|---:|---:|---:|---:|
| api-reference | 5 | 100% | 100% | 100% | 100% |
| baas | 5 | 100% | 100% | 100% | 100% |
| contract-dev | 15 | 93% | 93% | 93% | 100% |
| crosschain | 5 | 100% | 100% | 100% | 100% |
| platform | 20 | 95% | 95% | 100% | 100% |
| unanswerable | 10 | 0% | 0% | 0% | 0% |

## Evidence-gate failures

False refusals:
- `overview-002` Hyperchain 单链的交易吞吐量处于什么量级？
- `baas-003` 金融或政务强合规场景应选择哪种 BaaS 形态？为什么？

## Hybrid RRF misses

- `overview-002` Hyperchain 单链的交易吞吐量处于什么量级？ -> expected `platform/platform-overview.md`
- `gas-001` Gas 在 Hyperchain 中起什么作用？ -> expected `contract-dev/gas-billing.md`
