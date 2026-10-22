# 最终知识与 RAG 交付索引

实际本地版本：`kb-1d15bf97b31c0d90`。完整说明在
[最终交付记录](../../docs/qa/final-knowledge-20261021.md)。

- [正式发行目录](../../data/cdut/rag/versions/kb-1d15bf97b31c0d90/)：`snapshot.json`、
  `vectors.sqlite`、manifest、绑定目录、原件与不可变验收证据。
- [候选采纳包](../../data/cdut/rag/packages/freshman-final-20261021-v1/README.md)：
  本批逐条采纳依据、来源、正文及原件哈希。
- [120题来源审查](quality-cases.jsonl)、[来源标签变更依据](source-review-changes.json)。
- [实际回答观测](observations.jsonl)、[60题逐项审查](reviews.jsonl)、
  [逐题审查说明](answer-review-notes.json)、[正式门槛](quality-acceptance.json)。
- [复用与重测依据](acceptance-reuse-audit.json)：52 条保留、8 条受影响重测，
  不冒称同一最终源码第三次全量调用。
- [旧56题检索](legacy-retrieval.json)、[采集方自编34题检索](freshman-retrieval.json)、
  [检索计时条件](retrieval-latency.json)、[回答时延和活动账本](latency-and-budget.json)。
- [本地正式切换](local-publication.json)、[重载运行证据](local-runtime-proof.json)、
  [手机DOM复核](mobile-browser.json)、[平台入口后续修复](post-publication-validation.json)。
- [本轮代码差异](implementation.patch)、[文件及发行校验](delivery-manifest.json)。

发行归档：`output/final-knowledge-20261021/campuspilot-kb-1d15bf97b31c0d90.zip`。
校验哈希在 `delivery-manifest.json`，归档不含凭据或私有配置。

验收 54/60，6 道失败保留；本地回答 P50 5.75s / 样本 P95 8.65s，未达到原时延目标。
检索重合度不是回答正确率，缓存向量本地耗时不是联网端到端耗时。最终联网 P95、
真机及高德步行路线未验证，没有线上部署。
