# 迁移离线验证记录

完成日期：2026-10-11。状态：**DEVELOPER_OFFLINE_PASS**。
这是开发者验证记录，独立 QA、真实答案质量和生产性能仍为 PENDING。
上述离线验证阶段没有实际付费推理或部署。其后用户授权将完整代码提交并推送至
GitHub 重构交接分支；交接见 [Grok 重构说明](GROK_REFACTOR_HANDOFF.zh-CN.md)。

| 检查 | 结果 |
| --- | --- |
| Python 回归 | pytest 286 项全套通过，含迁移/发布/预算/引用/多轮边界测试 |
| 静态类型 | mypy strict（项目默认 backend/src、tests 及引用模块），57 个文件通过 |
| 代码检查 | Ruff 覆盖 backend/src、scripts、deploy、tests，通过 |
| 网页与地图 | app.js 语法检查；Node 测试 9 项通过，涵盖步行进度及周边查询取消/隐私边界 |
| 运行语法 | 两阶段候选包的 Python 源码通过 Python 3.12 AST 检查；本机执行环境为 Python 3.14.7，真实 Linux 3.12 执行留给独立 QA |
| 固定题 | 120 题哈希锁定，80 开发/40 保留；没有使用保留集调规则 |
| 离线检索 | 第二阶段开发集标注片段命中率 100%，仅为检索诊断；不能视为答案通过率 |
| 离线 API 计时 | 并发 2，三组冷/热各 100 次，总 600 次；模型未配置，simple/rag 的 limited 结果不计有效成功样本，不放行真实性能门槛 |

有一项 FastAPI/Starlette 测试客户端弃用提示；测试通过。本轮没有因此引入新依赖。

已覆盖的迁移边界包括：第二阶段阻断 Dify mock 传输仍可回答；模型/Jev 超时与未知引用；
历史、废弃、索引和限制内容；审核正文变化失效；导出期间源漂移；知识复制/指针切换
中断及回滚；目录文件与私有环境共同恢复；新目录和快照读权限在切换前继承；
八轮会话、跨会话隔离、事项/学年/人群污染、切换教师/简称消歧、银行卡与校园卡隔离；
缺关键余额前提的模型答案被拒绝；离线/缺件/NaN 性能/负成本/错误基线类型不放行。

本机报告与已捕获生产源码位于 .test-runs/runtime-migration/：

- delivery-offline-phase1.json、delivery-offline-phase2.json：最终源码的 80 题开发集报告。
- verified-offline-api-timing-phase2.json：离线完整 API 计时。
- production-capture/production-manifest.json、production-source.zip：实际部署的 45 文件，
  环境与服务配置仅哈希。不同于 Git HEAD。
- dify-console-audit/console-receipt.json：v9 发布页面/启用资料审计，仍为 NOT_LOCKED。
- delivery.json：检查结果、最终工件和逐文件/报告哈希；工件均为候选，不能直接作为上线验收。

完整运行及配置说明见 [迁移交付](RUNTIME_MIGRATION.zh-CN.md)。
阻断项保持：当前已发布 v9 DSL 导出限制、完整 Dify 管理 API 快照/映射、新模型/Jev
真实接入、完整 API 性能与答案评测、标签审核及独立 QA、第二阶段真实 Dify 网络阻断。
40 题保留集尚未用于接受/拒绝生产迁移，任务通过率 ≥95% 和速度目标均未宣称达标。
