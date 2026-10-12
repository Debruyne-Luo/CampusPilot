# CampusPilot 后端问答迁移交付

> 2026-10-12 状态更正：实际线上已运行 `31ed5bb` / `r-0f1805acf68e`，phase2、Agent loop on、
> hybrid，详情及核对证据见 [线上基线](LIVE_BASELINE.zh-CN.md)。下文保存早期迁移交付时的记录，
> 包括当时“尚未上线”“没有付费推理”的状态，不能用作当前部署结论。独立验收仍须另行完成。

## 历史交付记录

2026-10-11：**代码和离线验证交付，尚未上线，迁移验收未完成。**
批准范围见 [ADR 0005](adr/0005-backend-runtime-and-knowledge-publication.md)。
检查命令、证据与限制见 [离线验证记录](RUNTIME_MIGRATION_VALIDATION.zh-CN.md)。
此前的工作区改动随完整项目纳入 GitHub 代码分支；没有付费推理或远端部署。

## 当时证据与待完成项

| 项目 | 状态与证据 |
| --- | --- |
| 生产后端 | 只读捕获实际发布的 45 个文件、逐文件哈希、源码 ZIP；私有环境与服务配置只记录哈希 |
| Dify 工作流 | 控制台确认 v9，发布记录为 2026-10-09 22:41:23；发布版“导出 DSL”要求升级，不能取得完整已发布 DSL，因此基线为 NOT_LOCKED |
| Dify 资料 | 知识库 411a785a-6732-4e7f-838e-2720b19e60d9；启用文档 CampusPilot-campus-life-20261009-v2.txt，控制台显示 91 段；另 3 文档禁用。原文已下载并哈希，完整 API 片段状态快照仍待凭据 |
| 新审核包 | 审批、7 个原始资料文件哈希、44 块正文哈希已核对；21 来源、44 摘要块、12 办公室受限摘要，共 56 检索片段 |
| 固定题 | 120 题，80 开发、40 保留；事实、前提、来源、策略与片段标签已固定，独立标签核验仍为 PENDING |
| 验证 | 开发者单元、边界与兼容回归；离线开发集检索诊断；离线完整 API 计时。不能代替真实答案质量、部署时延或 Muse 独立 QA |
| 上线 | 默认 legacy；两阶段门槛未放行。新模型、OpenRouter Jev 和 Dify 管理凭据未用于真实推理 |

审计及报告在忽略目录 ``.test-runs/runtime-migration/``。当前生产留档在
``production-capture/``，控制台记录在 ``dify-console-audit/``。
旧本地 v6 DSL 不是当前 v9 基线。控制台草稿或只读页面截取也不能替代已发布 DSL。
参考 [Dify 版本管理](https://docs.dify.ai/en/cloud/use-dify/build/version-control)。

## 运行路径

| 模式 | 行为 |
| --- | --- |
| legacy | 保持现有线上行为 |
| phase1 | 后端统一校园、教师、事务和通知路由；目录直接调用现有权限业务函数；新生成模型直连。其他知识问答仍走冻结 Dify 应用 |
| phase2 | 后端完成全部问答；轻量词法 RAG 加生成模型。无需 Dify 应用密钥，不创建 Dify 聊天客户端，也不在故障时回退 Dify |

新增教师/事务直接回答规则默认为关闭，须通过绑定文件哈希和固定题的独立发布报告。
未认证时可调用模型，或在模型不可用时返回本地资料与 limited 状态。原有校园快速路径、
通知资料、卡片校验、地图及业务权限保持。

后端会话保留最近 8 轮和用户明确给出的身份/学年。同事项改问保留条件，切换事项清除
无关条件；一小时到期、进程重启及重置均清空，不导入 Dify 历史。第一阶段 Dify 回退
每次使用新上游会话，仅接收后端限定上下文，避免其独立记忆污染。
**Dify 应用 API 不能在这里按发布版本 ID 硬锁路由**：第一阶段仍须由维护方冻结被测
发布应用及其绑定资料，新正文维护与冻结运行资料隔离。此操作证据属于基线验收。

RAG 先筛身份、学年、时间、启停及历史/替代状态，再取 12 候选、最多 4 段生成。
中文重叠词组、标题/别名权重和词频区分只决定排序；分数不是可信度。
历史、废弃、索引和限制内容带类型及适用说明，不能变成现行办理规则。
模型引用必须属于本次来源集合；未知引用、不合法数字/URL/坐标被拒绝。
模型不能产生目录对象、地图坐标或工具权限。事实正确性仍由独立标签审核，不能仅靠
引用校验保证。故障时返回已收录资料和受限原因，不显示未经校验的生成答案。

## 私有配置

已创建仓库外文件：

- ``C:\Users\21207\AppData\Local\CampusPilot\migration.ps1``：入口、模型 ID、价格及路径。
- ``secrets\model-key.txt``：新生成模型密钥。
- ``secrets\openrouter-jev-key.txt``：OpenRouter Jev 密钥。
- ``secrets\dify-dataset-key.txt``：Dify **知识库 API** 密钥，与应用聊天密钥分开。

每个 TXT 只填一行密钥，不加引号、变量名或 KEY=。不得把密钥发到聊天或写入仓库。
读取器要求绝对仓库外路径；API_KEY 与 KEY_FILE 同时设置会拒绝启动。
Windows 密钥目录只授权当前用户和 SYSTEM。生成脚本保留已存在的文件内容：

```powershell
./scripts/setup_migration_config.ps1
. "$env:LOCALAPPDATA\CampusPilot\migration.ps1"
```

生成模型填写 CAMPUSPILOT_MODEL_BASE_URL（HTTPS API 基址，代码追加 /chat/completions）
和 CAMPUSPILOT_MODEL。若服务使用 OpenRouter，基址为 https://openrouter.ai/api/v1。
该生成模型与 Jev 决策模型分开配置，未替用户选择具体生成模型。

Jev 使用 typesafe/jev-1.13，调用 **https://openrouter.ai/api/alpha/decisions**，
不是把它当普通聊天模型调用。价格字段需按实际账单/当前供应商文档核对后填写；
默认留空，价格未知不批跑。参见
[OpenRouter Jev 接口说明](https://openrouter.ai/blog/insights/what-is-jev/)、
[Jev 参考项目](https://github.com/kerpopule/hermes-jev-skills)及
[影子到线上设计](https://github.com/kerpopule/hermes-jev-skills/blob/main/docs/shadow-to-live.md)。
参考代码只作设计依据，不加载其 Skill 来授予运行权限。

Jev 从固定公开题和校园摘要获得 Choice/Noul/Score 建议：直接/生成/澄清、追加检索、
充分性和候选重排。手机号/邮箱脱敏，拒绝个人账号、位置和非公开输入。返回项须在
候选集合内；超时、错误、低置信度保留原候选。没有线上 Jev 调用点。
报告以固定标签比较漏检、无效检索、上下文命中、耗时和成本，不以 Jev 自评分验收。

## 知识维护链

审核包已作为候选留在 data/cdut/rag/approved-20261010/，并生成用于本地验证的
bootstrap.json，版本 ``kb-db2f7f77dc388555``。未写入生产 current.json。
12 个办公室摘要仅参与问答，保留电话/地点待独立核验的限制，不生成办公室卡片或导航点。
同 URL 的不同版本、来源 ID、适用事实范围被保留，不按 URL 覆盖。

以下在维护机运行，输出放在仓库外；先读取完整 Dify 配置、文档、片段及启停状态。
导出全量读两遍，任何源漂移取消操作，命令不修改 Dify：

```powershell
$work = "$env:LOCALAPPDATA\CampusPilot\knowledge"
.venv/Scripts/python.exe scripts/knowledge_release.py export-dify --dataset 411a785a-6732-4e7f-838e-2720b19e60d9 --output "$work\dify.json"
.venv/Scripts/python.exe scripts/knowledge_release.py init-sidecar --snapshot "$work\dify.json" --knowledge data/cdut/rag/bootstrap.json --output "$work\sidecar.json"
```

sidecar 保存来源、正文审批、适用对象、日期、类型、稳定片段 ID，以及 Dify 文档/片段 ID。
模板只建议正文哈希完全相同的匹配，全部标为 review_required。维护方核对后设为 false；
未匹配片段须建立有来源和审核的新记录，或明确填写 exclude_reason，不得以自动排除
躲过旧有效资料保留要求。local_only_chunk_ids 必须明确声明，新审核包未导入 Dify 的
正文只能在确认维护归属后显式纳入。正文变化或映射失配会使编译失败。
当前一般分段可发布；层级 child_chunks 尚须明确审核归一化，不能静默丢弃。

```powershell
.venv/Scripts/python.exe scripts/knowledge_release.py compile --snapshot "$work\dify.json" --sidecar "$work\sidecar.json" --output "$work\candidate-v1"
.venv/Scripts/python.exe scripts/knowledge_release.py preview --candidate "$work\candidate-v1" --store "$work\store"
.venv/Scripts/python.exe scripts/knowledge_release.py publish --candidate "$work\candidate-v1" --store "$work\store" --expected-current none
# 替换版本时填入预览中的 before；回滚也必须匹配当前版本。
.venv/Scripts/python.exe scripts/knowledge_release.py rollback --store "$work\store" --version kb-OLD_VERSION_ID --expected-current kb-CURRENT_VERSION_ID
```

发布包包含纳入/排除清单、原始快照、证据映射、版本、逐文件哈希。先在临时目录构建
完整版本并复核，再原子切换 current.json；单请求持有同一快照。中断不会覆盖旧指针，
版本回滚也原子切换。崩溃留下的 .publication.lock 只能在确认维护进程已退出后处理。
不要把本地测试 store 当作线上发布证据。线上 store 为 CAMPUSPILOT_DATA_DIR 下的 rag；
维护命令须在受保护的维护环境中操作该完整 store，保留版本目录及备份。
KnowledgeStore 的现有 6 条通知/指南继续独立保留；完整现行 Dify 语料的映射仍待基线
导出及逐段审查完成，不能以新包覆盖它们。

## 基线、评测与发布门槛

先把已发布脱敏 DSL、发布记录、全量知识快照和实际生产文件清单锁定。
scripts/lock_runtime_baseline.py 的 workspace-only 只证明工作区哈希，不能生成 LOCKED
发布基线。Git HEAD 与实际生产运行版本分别记录，dirty/untracked 文件也纳入。
发布 receipt 须包含 app_id、workflow_id、published_version、observed_at、dsl_sha256、
export_kind=published 和 verified_against_publish_record=true；禁止将草稿标记为发布版。

```powershell
.venv/Scripts/python.exe scripts/lock_runtime_baseline.py --workspace-only --output .test-runs/runtime-migration/workspace-final.json
# 取得真实发布证据后：
.venv/Scripts/python.exe scripts/lock_runtime_baseline.py --published-dsl "$work\published.yml" --published-receipt "$work\published-receipt.json" --knowledge-snapshot "$work\dify.json" --production-manifest .test-runs/runtime-migration/production-capture/production-manifest.json --output "$work\baseline.json"
```

离线诊断不发起外部推理，默认只跑开发集；保留集不用于调规则：

```powershell
.venv/Scripts/python.exe scripts/evaluate_runtime.py --stage phase1 --output .test-runs/runtime-migration/dev-phase1.json
.venv/Scripts/python.exe scripts/evaluate_runtime.py --stage phase2 --output .test-runs/runtime-migration/dev-phase2.json
.venv/Scripts/python.exe scripts/benchmark_runtime.py --stage phase2 --samples 100 --output .test-runs/runtime-migration/api-offline.json
```

离线 RAG 的标签片段命中是检索诊断，**不是 95% 答案通过率**。
离线计时为 ASGI 完整 JSON 答复、并发 2、每组冷/热各 100 次；无模型的 limited 样本
不会充作生成或简单路径的有效成功样本。不能把这些数值作为真实部署的性能验收。

真实推理只在凭据、已知价格、LOCKED 基线和独立环境就绪后显式启用：

```powershell
.venv/Scripts/python.exe scripts/evaluate_runtime.py --stage phase2 --split all --live --shadow-only --baseline "$work\baseline.json" --output "$work\shadow-phase2.json"
```

shadow-only 只做候选决策/重排，答案质量从完整 API 采集，避免重复付费生成。
外部调用共用仓库外每阶段账本：5 美元与 1,000 次先到即停。先保守预留，再按已知
用量结算；未知用量/超时/中断保留预留，不因重启免费重跑。停止时保存部分报告，
门槛仍不放行。不得修改账本上限或换目录绕过预算。

scripts/collect_api_evaluation.py 采集固定题的完整 API 答复，双客户端隔离会话，并发 2。
显式传入 --live、LOCKED 基线、候选 runtime-manifest.json、测试环境 receipt、
价格及已核验的输入/输出和每 API 最大推理次数，使用同一阶段账本。
生成、Dify 和 Jev 的上限都计入。Dify 价格可通过 DIFY_EVALUATION_INPUT_USD_PER_MILLION
和 DIFY_EVALUATION_OUTPUT_USD_PER_MILLION 单独配置。计数保守预留可能先触发上限，
预算不足时不减少有效样本要求。

环境 receipt 包含 environment、model_configuration={base_url,model} 和经核验的
same_deployment_environment。--mode answers --split all 生成 120 题 API 答复；
--mode timing --case-id 固定题ID --path simple/rag/dify_simple --temperature warm/cold
--samples 100 分别采样。cold 还须提供 --restart-argv-file（JSON argv 数组），只指向
**独立测试服务**，每两请求实际重启一次并留启动时间；仅新会话不算冷启动。
该命令会执行明确指定的重启命令，不应指向生产服务。合并工具为 merge_api_timing.py；
显式 reuse-frozen-dify-baseline 仅允许在环境、代码/资料、固定题和原基线哈希全部不变时
复用前阶段 Dify 测量。发生任何字节变化必须重新测量，不能靠改阶段标签复用。
现有生产日限额 100 不被放宽；独立评测环境若触发限流，应保留失败记录并安排足够
测量窗口，不能将 429 或降级结果计为有效样本。

独立 QA 使用 evaluation/runtime-migration/independent-qa.template.json 的副本，
保存仓库外，核验标签、全部 120 题和原能力基线；审查答案/性能/影子/基线报告哈希。
填入真实测试文件哈希、测试环境、模型配置、时间和审核人；不要填写模板中的虚构 PASS。
开发者测试不能替代 Muse。第二阶段必须提供阻断 Dify 网络的真实问答验收。

check_migration_gate.py 绑定上述 5 个报告与当前文件/固定题哈希，并检查：

- 总体及保留集 ≥95%；原能力不退步；关键事实错误、前提缺失、无依据断言均为零。
- simple 冷/热各 ≥100 有效样本、P95≤2秒，且较同环境 Dify 至少快50%；
  第二阶段 rag 冷/热各 ≥100 有效样本、P95≤15秒。
- 真实完整 API、完整 Jev 影子样本和预算、独立质量/故障/权限/地图/移动端 QA；
  phase2 的 Dify 网络阻断证据。

任一缺项、字节漂移、模型变化或离线报告替代真实报告都会 FAIL，新增直接规则保持关闭。
publish_runtime.py 默认只准备本地固定 ZIP 与哈希；--publish 才进入受保护的 VPS 更新，
并要求同阶段 PASS 报告与经测模型配置。复用现有文件防漂移、备份、健康验证及回滚；
私有环境先备份，配置与文件故障共同回滚；新源码目录继承旧目录的权限/所有者，
知识版本与指针继承已可读快照的权限，并在原子切换前设置。部署前仍须人类 Review 与独立 QA。
更换知识版本会使已加载快速规则失效；重新启动时资料哈希变化也使旧认证报告失效，
需更新匹配报告，不能沿用旧规则审批。

## 扩展接口

Retriever、Reranker、DecisionPolicy 与 ProductionModel 相互独立。
RetrievalHit 共享稳定 chunk/source ID 和知识版本；VectorRetriever 的 VectorIndexBinding
另绑定 embedding_model_version 和维度。未来向量/词法候选可合并去重后重排。
CandidateDecisionPolicy 只接受预设候选 ID；后续 Skill/工具建议仍须应用权限核验，
不能让模型或 Jev 扩大权限。本轮未启用向量服务、Skill 自动选择或工具决策。
