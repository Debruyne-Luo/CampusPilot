# 最终评分：新测试集 eval-fresh-20261011（只跑一次）

- 提交：handoff `2fafe091`；生成模型 deepseek-flash（关思考）；Jev typesafe/jev-1.13，上限 $0.30。
- 测试集：90 题，60 可答、30 拒答（拒答题 target_chunk_ids 为空，topic 为 no_answer）。没有调参，没有改代码。下表全部是聚合数字，不含题目原文。

| 指标 | A（Jev off，grounding flag，生产默认） | D（Jev on，当前默认） |
|---|---|---|
| 拒答召回 | 2/30（6.7%） | 22/30（73.3%） |
| 误拒 | 9/60（15.0%） | 12/60（20.0%） |
| 引用精度 | 0.256 | 0.314 |
| 引用到 gold 的答案 | 38/51（74.5%） | 37/48（77.1%） |
| 拒答题无引用 | 3/30 | 23/30 |
| 延迟 p50 / p95 | 3132 / 4110 ms | 3158 / 4566 ms |
| 降级 | 5/90 | 3/90 |
| DeepSeek 成本 | $0.04194（183 次调用） | $0.02047（161 次调用） |
| Jev 成本 | — | $0.00808（69 次调用；unsure 20/69 = 29%；p50 302 ms） |

检索层（hybrid，60 道可答题）：R@1 0.650，R@5 0.908，MRR@20 0.819，hit@5 0.933，miss@20 2。lexical 的 R@5 为 0.817，vector 为 0.775。

## 失败分布（按 topic）
- teacher_lookup（12 题）：两组都是 6 题误拒，另有 6 题没引用 gold 知识片段。老师名录问答走的是名录工具，不走知识库，Jev 不改变这部分。这是两组误拒的最大来源。
- no_answer（30 题）：A 答了 28 题，D 答了 8 题。
- D 比 A 多出的误拒在 tuition_payment、job_fair、mail，各 1 题，都是 Jev 判 clarify 造成的。fee_invoice、clubs 两组各 1 题误拒。
- 没引用 gold：tuition_payment（A 3 题 / D 2 题）、clubs、vpn、repair 各 1 题。
- 降级：invalid_response 在 A 4 次、D 3 次；ocr_example_amount 在 A 1 次。

## 结论
在没见过的题上，Jev on 把拒答召回从 6.7% 提到 73.3%，代价是误拒多 3 题（15% → 20%），离 dev 定的 ≤2% 目标很远。误拒的主体是老师名录类问题，与 Jev 无关。
