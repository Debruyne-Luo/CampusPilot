# 2026-10-21 新生体验增量证据

公开问题与公开学校资料，不包含密钥、个人账户、学生会话或个人位置。
结果适用于基线 `715555e13829395aeef4abb89706f3f6a3f9d51a` 加本轮修改，
不是已部署版本。完整结论与限制见 [核验报告](../../docs/qa/student-experience-20261021.md)。

| 文件 | 用途 |
| --- | --- |
| `implementation.patch` / `changed-files.json` | 相对本轮开始时工作区的差异及前后哈希，保留此前修改 |
| `verification-manifest.json` | 最终源码、测试、前端与候选版本的身份及检查结果 |
| `smoke-initial.json` / `smoke-intermediate.json` / `smoke-final.json` | 小规模真实模型、Jev 和 Search/Fetch 记录；三个阶段不能当作重复独立的保留集 |
| `browser-check.json` / `browser-stream-check.json` | 桌面/手机交互与合成流式响应回归 |
| `knowledge-baseline-development.json` / `knowledge-development.json` | 同一开发集上的词法检索诊断及正式门槛状态；不包含回答质量通过证据 |
| `budget.json` / `budget-reconciliation.json` | 现有活动总预算及本轮请求归账，不是供应商发票 |

初次小样本暴露重复提醒和无关补查，随后修正；中间性能脚本误复用了已满 40 轮的会话，
导致 50 次中后 10 次 HTTP 429。保留该失败记录，不把快速错误计入最终成功时延。
最终为十个独立会话、六种公开问题、60 次进程内 HTTP；不是生产并发或移动网络性能。

修正知识候选位于
[`student-life-integrated-20261021-v2`](../../data/cdut/rag/candidates/student-life-integrated-20261021-v2/)，
候选输入与原件索引位于对应 [package](../../data/cdut/rag/packages/student-life-integrated-20261021-v2/)。
候选保持 pending，未生成向量或切换发布指针。用户独立 DeepSeek 会话的新生采集不属于这些实测。
