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
