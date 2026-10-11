# 混合检索（P2）

记录日期：2026-10-11（北京时间）。

## 结构
- `retrieval/bm25.py`：BM25（k1=1.2，b=0.75），分词仍为中文 2/3-gram 加英文/数字词；标题与别名的词频权重为 3.4（单字段 BM25F）。硬过滤 `eligible()` 包括：启用状态、有效期、历史版本、适用对象、学年。三种检索方式共用这套过滤，并且在融合之前执行。
- `retrieval/vector.py`：每个快照对应一个 SQLite 单文件向量索引（`vectors.sqlite`），记录 knowledge_version、embedding_model、dimensions，以及每个片段的 `text_sha256`。加载时版本、模型、正文哈希或覆盖范围任一不符就拒绝加载。查询优先用 sqlite-vec，扩展加载失败时退回 numpy，再不行用纯 Python。
- `retrieval/hybrid.py`：用 `CAMPUSPILOT_RETRIEVAL_MODE` 选择 lexical / vector / hybrid；hybrid 用 RRF（k=60）融合 BM25 与向量两路各前 20 条。拿不到查询向量时退回 BM25，并标记 `degraded`。
- `llm/embedding.py`：调用 Cloudflare Workers AI 的 `@cf/baai/bge-m3`（1024 维）。带超时、可重试错误（429/5xx）的有限退避重试、每批最多 50 条、查询 LRU 缓存。凭据只从 `CF_ACCOUNT_ID` / `CF_API_TOKEN` 读取，经 `Settings` 传入，不会出现在 repr 或报错信息里。
- 运行时（phase2）：`/api/chat` 进入同步的 `prepare()` 之前，先异步预取问题的向量写入缓存；同步检索只读缓存，缓存未命中或服务失败就只用 BM25。注意：多轮追问时 `prepare()` 会把问题改写成"上一事项；追问"，改写后的文本不在缓存里，这类请求目前只走 BM25。
- `search_knowledge` 工具：注入快照库后改用混合检索，返回片段、来源、知识版本、检索模式和是否降级。

## 发布与版本绑定
```sh
uv run python scripts/knowledge_release.py embed --candidate <候选目录>   # 写入 vectors.sqlite 并登记到 manifest
uv run python scripts/knowledge_release.py publish --candidate <候选目录> --store data/cdut/rag --expected-current <版本|none>
uv run python scripts/knowledge_release.py embed-bootstrap --store data/cdut/rag  # 重建 bootstrap.vectors.sqlite
```
索引登记在候选目录 manifest 的 `files_sha256` 里，`publish()` 会把它和 `snapshot.json` 一起复制到不可变的版本目录，再原子切换 `current.json`。索引被篡改时校验和不通过，无法发布。

## 评测（2026-10-11，真实 Cloudflare 向量）
命令：`uv run python scripts/evaluate_retrieval.py --output evaluation/retrieval-eval-20261011.json`
数据：`evaluation/runtime-migration/cases.jsonl` 中标注了 chunk_ids 的 56 题（开发集 38 / 保留集 18，每题 1 个目标片段），bootstrap 快照 `kb-` 版本见结果文件，向量后端为 sqlite-vec。

| 方式 | 全部 Recall@5 | 全部 MRR@20 | 开发集 R@5 / MRR | 保留集 R@5 / MRR |
| --- | --- | --- | --- | --- |
| 旧版加权 TF-IDF（P1 的 LexicalRetriever，对照） | 0.9821 | 0.8661 | 1.0000 / 0.8816 | 0.9444 / 0.8333 |
| **BM25（lexical）** | 0.9821 | **0.9405** | 1.0000 / 0.9693 | 0.9444 / 0.8796 |
| 向量（vector） | 0.9821 | 0.8929 | 1.0000 / 0.9211 | 0.9444 / 0.8333 |
| 混合（hybrid，RRF） | 0.9821 | 0.8810 | 1.0000 / 0.9079 | 0.9444 / 0.8241 |

结论（如实记录）：
- BM25 比旧 TF-IDF 的 MRR 从 0.866 提高到 0.941，召回不变。
- 在这套题上，向量和混合检索**都没有超过 BM25**。原因是题目大多直接沿用片段标题和关键词，词面重合度很高，BM25 已接近上限（Recall@5 = 0.98）。这套题测不出语义检索在同义改写、口语化问法上的优势。
- 没有调参；保留集只用于报告结果。要证明混合检索的价值，需要另建一套"口语化 / 同义改写"题，并由人工独立标注。

## 口语化检索调参（2026-10-11，rag/02-tuning）

- 测试集：`/workspace/cp-knowledge/eval-colloquial-20261011.jsonl`（99 题，6 题拒答；与仓库 `evaluation/colloquial-heldout-20261011` 同题）。只用于最终测量一次，未参与调参。
- 开发集：`evaluation/dev-colloquial-20261011/cases.jsonl`（118 题 = 50 道依据知识库条目标题手写的口语问法 + 6 道库外拒答题 + `evaluation/colloquial-20261011` 64 题；按规范化文本去掉与测试集重复的 2 题），由 `build_dev.py` 生成。
- 改动：
  1. `stale=true` 的事实类条目，即使来源 `temporal_status=historical`，也保留为候选并降权（`STALE_WEIGHT=0.85`）；`historical/deprecated` 类条目、`superseded` 来源、超过 `valid_until` 的条目仍硬过滤。`excluded_from_retrieval` 条目在导入时即被丢弃，不进入快照与向量索引（新增回归测试）。
  2. BM25 查询加口语→官方用语扩展（`bm25.SYNONYMS`，只追加不替换）。
  3. 加权 RRF：`RRF_K=10`，权重（词法 1.0，向量 1.25）。
- 复现：`uv run python evaluation/eval_colloquial.py --cases <file>`；开发集网格搜索：`uv run python evaluation/tune_dev.py`。报告见 `evaluation/reports/`。
- 检索层不做拒答：向量相似度阈值 0.35–0.55 在开发集上无法区分库外问题，拒答依赖下游 agent 无答案判定。

## 本地"无依据"拒答策略（2026-10-11，rag/03-local-refusal）

实现 `rag.DecisionPolicy`：`retrieval/grounding.py`（`LocalGroundingPolicy` / `assess`），纯本地、确定性，不调用模型。

- 片段判定为 grounded：查询向量余弦相似度 ≥ 0.60；或 ≥ 0.52 且 BM25 与向量两路排名都 ≤ 3（两路一致）。
- 展示的前 4 条里没有 grounded 片段 → `insufficient`。没有查询向量（lexical 模式或嵌入服务故障）→ `unassessed`，保持旧行为。
- 查询词覆盖率、RRF 融合分记录为信号但不参与判定：开发集上二者在相似度 + 两路一致之外没有额外区分度。
- `search_knowledge` 每条 hit 带 `grounded`，结果带 `grounding.decision`；判为 `insufficient` 时片段不交给模型、不进入可引用集合。
- Agent：模型返回 `empty` 或最终回答为"已发布资料中没有足够依据回答"时，不再回退展示 citations / excerpts；降级摘要 `_summary` 只用 grounded 片段，没有就给出无依据提示（`result_status=empty`）。

阈值只在开发集上选：`evaluation/dev-colloquial-20261011`（112 可答 + 6 拒答）+ `evaluation/refusal-20261011/dev.jsonl`（25 拒答）。
选择规则：误拒率 ≤ 2% 的前提下拒答召回最高（扫描见 `evaluation/reports/refusal-dev.json`）。
测试集只跑一次：`evaluation/colloquial-heldout-20261011`（99 题，只测不调）+ `evaluation/refusal-20261011/test.jsonl`（25 拒答）。

| 集合 | 指标 | 之前（仅零命中拒答） | 之后 |
|---|---|---|---|
| dev | 拒答召回 | 0/31 | 16/31（51.6%） |
| dev | 可答误拒 | 0/112 | 2/112（1.8%） |
| test | 拒答召回 | 0/31 | 15/31（48.4%） |
| test | 可答误拒 | 0/93 | 8/93（8.6%） |

检索排序未改变：hybrid dev R@5 0.9643 / MRR@20 0.8163，test R@5 0.8925 / MRR@20 0.8178，与 rag/02-tuning 报告一致。

已知局限：测试集误拒明显高于开发集，多为错别字（"辅道员""转专页""心里中心"）和长口语句，向量相似度偏低；"借了 X 但问 Y"类对抗问题（如"校园卡能在校外超市刷吗"）检索信号无法区分，需要后续相关性/充分性判断。

`evaluation/refusal-20261011/` 的 50 题由 agent（Grok Bot）于 2026-10-11 撰写，模拟成理学生提问，非真实学生数据，未经人工复核（`label_status: authored_unreviewed`）。
