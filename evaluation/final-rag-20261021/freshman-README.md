# 新生入学检索评测集（2026-10-21）

**标签状态：`authored_unreviewed`。** 34 题由撰写新生片段的同一 agent 编写，问题大多能从
片段标题/正文反推，存在标注泄漏风险。它适合做 smoke test 和回归，不适合当作独立基准，
也不应用于调参后宣称“效果提升”。正式使用前应由未参与片段撰写的人独立复核或重写。

- `cases.jsonl`：30 道可答题 + 4 道库外/动作题；可答题带 `chunk_ids`。
- 覆盖：报到、交通、户口、团组织、档案、缴费、贷款、绿色通道、公寓、报修、校医院、
  军训、学院电话、砚湖易办、账号激活、安全手机、体检/疫苗、心理咨询、迎新网、学生邮箱、
  入学时间线、校区、餐厅、一卡通。
- 运行（当前只有词法，因为候选没有向量）：

```powershell
.venv\Scripts\python.exe evaluation\eval_colloquial.py `
  --cases evaluation\freshman-20261021\cases.jsonl `
  --snapshot-dir data\cdut\rag\candidates\pending-20261021-freshman `
  --modes lexical `
  --output evaluation\reports\freshman-lexical-20261021.json
```

2026-10-21 词法结果：R@1 0.9167，R@3/R@5 1.0，MRR@20 0.9667，可答题空结果 0，
拒答题正确 0/4。拒答应由 grounding/agent 处理，不应由检索层承担。

完整审计与优先级见 [知识库与 RAG 审计](../../docs/KNOWLEDGE_RAG_AUDIT_20261021.zh-CN.md)。
