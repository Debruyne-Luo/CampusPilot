# 知识库优化与重采实施记录

日期：2026-10-17；代码基线 `main@01d5318` 加本工作区改动。批准范围见
[ADR 0007](adr/0007-knowledge-quality-and-recollection.md)。本轮形成可检查的候选和本地实现，
尚未完成全量重采、真实模型验收或发布。用户原有设计、模型资产及资料采集改动均保留。

## 实际版本与交付物

- 只读核验的线上版本：release `r-62d8e21843ee`，commit `eba182cce42aa8ff506a04aa3738cdf5ced818d6`，
  bundle `approved-20261011b`，知识版本 `kb-f08fa4fd8b583700`，158 来源、287 片段。
- 本地活动基线：`data/cdut/rag/versions/kb-229ee34eba99ef34/`，176 来源、322 片段。
  `data/cdut/rag/current.json` 保持指向此版本；未按旧文档回退资料。
- 本轮联合候选：`data/cdut/rag/candidates/rebuild-20261017/`，`kb-6044dcc621f40bbe`，
  schema v2，176 来源、324 片段。47 条已有明确修订绑定；其余不补造原文元数据。
- 结构化部分：36 项服务，其中 4 项保留有证据的完整流程、32 项指南。完整度不等于现时可办，
  原有时间和可用性限制仍保留。目录原始记录、32 项正文及字段证据随联合 manifest 绑定。
- 审查包：`output/knowledge-rebuild-20261017/knowledge-review-final-v2.zip`，148 个文件，
  SHA-256 `683ea637694aadf41ac33956a342defe259b0d6ffbae5aa2acb6c955b381946c`。
  这是审查工件，`release_ready=false`，不是可直接部署的完整发布包。

原始核验记录：`output/knowledge-rebuild-20261017/live-baseline.json`；
候选状态：候选内 `review-status.json`。早期中间候选保存在 `output/.../superseded/`，不作为最终版本。

## 实现与接口

沿用 `official_knowledge` 的提取、标注、编译流程；Firecrawl 只负责采集适配，不另建采纳入口。
`official_capture` 保存采集参数、最终 URL、正文及响应哈希、分页和图片依赖；
挑战页、失败、截断和未核对 OCR 均不能以 API 成功状态获得完整正文身份。

v2 绑定文档修订、原文定位、标题/条款/父章节、条件及例外。旧 v1 哈希不变，部分修订更新不会
将未变旧条款重标为新修订。失败保留上次成功内容；显式废止必须有原文依据。
直接 RAG、Agent 工具和多轮继承共用校区、人群、学年及时间规则。
章节扩展受来源、修订、范围、数量及字符预算约束；预算不足时说明缺证据，不截断后假装完整。
引用仅绑定最后实际保留的证据，并保留适用限制。

服务新增 `information_level=directory|guide|procedure`。旧记录默认指南；只有明确完整流程可新建
步骤清单。指南展示已知事实、入口及缺失信息，浏览器原有清单内容和勾选进度保持可读。
联合候选将目录与索引绑定；`knowledge_release.publish()` 拒绝只发布其中 RAG 的操作。

详细契约见 [知识治理](KNOWLEDGE_GOVERNANCE.zh-CN.md)、
[办理清单](HANDLING_CHECKLIST.zh-CN.md) 和 [分层评测](KNOWLEDGE_EVALUATION.zh-CN.md)。
没有引入独立向量数据库、GraphRAG、新嵌入或新重排模型。

## 免费采集的实际结果

Firecrawl 小试已串行执行固定 12 个入口，未自动重试、充值或升级。按请求预留 22 credits；
账户余额从 1382 变为 1363，观察差值 19。预留量与供应商计费差值分别记录，不把两者混为精确账单。
调用前后检查余额，PDF 最多 10 页，未知结果不自动重新提交。

结果为 9 项访问失败、1 项 PDF 截断（10/18 页）、2 项公众号待核验。
普通校内页面仍有 412 或供应商错误，不能认定此方法已经适用于所有格式。
公众号发现 34 个图引用（含 2 个头像），其中 32 个正文图片未核对；可读 Markdown 不代表资料完整。
本轮没有自动采纳任何 Firecrawl 返回的正文。

定向补齐另经公开原件和本地人工可视核对完成：取得 PDF 18/18 页，更新原有第 56–58 条片段；
核对借户口本、心理预约两张官方原图并新增两条精确转录。共 3 文档、3 变化片段，来源数不增加。
2019 PDF 的现时有效性和两图适用校区等未知项仍为 unknown。2 篇公众号因缺原图保持 incomplete，
编译拒绝其不完整正文并保留旧成功记录。不能从定向成功推导全量采集成功。

来源清单由现有来源及已保存目录形成，306 条登记、296 个去重 URL，尚不是学校全站完整清单。
Firecrawl 后原始状态为 191 待复核、9 访问失败、2 待审、1 截断、103 范围外；
定向复核作为独立覆盖层记录，不覆盖原始采集状态。后续仍需核对栏目分页、附件及教师/部门缺口。
免费额度尚有余额不代表继续使用相同方法能够解决已观察到的访问和图片问题。

记录位于 `output/knowledge-rebuild-20261017/source-inventory.json`、`source-coverage.json`、
`firecrawl/collection.json` 和 `source-review.json`；原件包见
`data/cdut/rag/packages/rechecked-20261017/README.md`。口径及剩余清单见
[来源覆盖边界](KNOWLEDGE_SOURCE_BOUNDARY_20261017.zh-CN.md)。

## 评测结果与发布阻断

120 个场景已冻结，60 开发、60 保留，六类各 20；24 个来源/事项组隔离。
套件 SHA-256 为 `571902a1e3d42d96103add4218e6b55da57e3d37579826c9013b03ead6fc9c1e`。
独立原文审查完成 38 题；82 题仍为 draft。168 个锚中 54 个通过原件与哈希核对，114 个仍缺核验。
这些状态不表示人工复核或政策现时有效。金标修正理由及原件见
[金标审查记录](research/knowledge-gold-review-20261017.md)。

冻结后只运行了一次基线/候选的完整离线词法对照。开发集需检索的 45 题：两版 Recall@5 均为
0.9889，完整证据覆盖均为 0.9778。保留集需检索的 39 题：Recall@5 从 0.9744 降到 0.9615，
完整证据覆盖从 0.9744 降到 0.9487。32 个历史或已停用资料边界题不要求检索返回旧规则，
仍需实际回答与行为审查。未知适用范围命中仍很普遍，不能把零已确认范围错误解释为数据完整。

退步场景 `kq-076`：网络报修图文差异题的正文证据从第 4 降到第 6 位，新增两条流程图排在其前。
因此完整证据未进入 Top 5。此结果作为发布阻断保留；没有依据保留集调整排序或金标。
运行时章节扩展与实际答案能否补齐，必须另有真实观测，不以推测覆盖本次退步。

旧 118 题开发回归的词法 Recall@5 两版均 0.9077；MRR@20 从 0.7113 降到 0.6994，
4 题首个金标排名下降，Top 1 命中也有下降。因此尚不能宣称原有核心能力不退步。
逐题比较保存在 `output/knowledge-quality-20261017/retrieval-regression-final.json`。
旧“无金标空检索”和“展示摘录重合”均已改名，不再当作正确拒答或引用事实正确。

最终逐题报告在 `output/knowledge-quality-20261017/frozen-{baseline,candidate}-final.json`；
旧集回归为 `legacy-dev-{baseline,candidate}.json`。它们没有调用文本或嵌入模型，
实际回答及引用支持均为 unassessed，不能解释成 0% 正确率或通过 54/60。

目前发布阻断包括：

- 3 条新增/修改文本缺匹配 BGE-M3 向量。321 条输入可精确复用旧向量；尚未生成并校验最终 324 行索引。
- 82 题金标和 114 个原文锚仍缺完整来源审查；来源清单仍有明确缺口。
- 缺真实文本模型的 60 题观测及逐题审查，金额、期限、资格、地点与步骤零错误门槛尚未验收。
- 已观察到词法排序退步，需要独立开发样本诊断与新的冻结验收轮次。
- 完整自动化的 Windows 既有失败与实际运行结果见下节，不能忽略失败而宣称全绿。

## 重复执行

以下命令只读旧版本，不切换活动知识指针。输出目录必须是新的空路径；不要覆盖不可变候选。

```powershell
# 定向采集包的原件、篡改拒绝、幂等及失败保留检查（无网络调用）
.venv/Scripts/python.exe -X utf8 scripts/review_collected_sources.py --verify

# 先编译3个变化片段，再绑定结构化目录与旧向量提供者
.venv/Scripts/python.exe -X utf8 scripts/official_knowledge.py compile --package data/cdut/rag/packages/rechecked-20261017 --annotations data/cdut/rag/packages/rechecked-20261017/annotations.json --base data/cdut/rag/versions/kb-229ee34eba99ef34 --output output/knowledge-rebuild-20261017/reproduce-base
.venv/Scripts/python.exe -X utf8 scripts/build_knowledge_review.py --base output/knowledge-rebuild-20261017/reproduce-base --vector-donor data/cdut/rag/versions/kb-229ee34eba99ef34 --directory data/cdut/rag/candidates/services-20261017 --output output/knowledge-rebuild-20261017/reproduce-joint --archive output/knowledge-rebuild-20261017/reproduce-review.zip

# 开发集默认离线；保留集仅用于冻结后的最终比较，不据其调参
.venv/Scripts/python.exe -X utf8 scripts/evaluate_knowledge_quality.py --snapshot data/cdut/rag/candidates/rebuild-20261017/snapshot.json --output output/knowledge-quality-20261017/reproduce-development.json
```

真实答题采集器已接入现有 `AgentRunner`、工具及文本模型接口，金标不会送给答题模型。
配置必须在仓库外，明确 `free_only: true`、服务地址、模型、密钥文件及 `max_requests`。
每次 HTTP 请求先持久预留预算，首轮只跑两题；超时或未确认请求不自动重发。
更换输出路径也不能绕过同题的未知请求保护。评测日期通过独立上下文传到 Agent 与工具，
不覆盖用户适用范围，不改变并行请求的真实日期；固定题不因明天运行而变成今天的政策判断。
先用已有免费文本模型跑通两题，再根据实际每题工具调用次数决定足够且免费的请求上限。
不因有文本额度就推定同时拥有 BGE-M3 额度；查询向量缓存缺失时会明确记录词法降级。

```powershell
.venv/Scripts/python.exe -X utf8 scripts/collect_knowledge_answers.py --config C:/path/outside-repository/free-model.json --snapshot data/cdut/rag/candidates/rebuild-20261017/snapshot.json --limit 2 --output output/knowledge-quality-20261017/candidate-answers.jsonl
```

两题检查后，同命令去掉 `--limit 2` 可续跑开发集；保留集需显式 `--split holdout`。
观测及审查绑定问题、知识版本和回答哈希，不能把模型自评分填成验收结果。
截至本记录，用户表示有免费资源，但尚未提供服务与仓库外配置路径；没有运行任何真实文本答题。

## 自动化与回滚

Python 全套及审查后回归结果见机器记录；Node 84 通过；Ruff 通过，Mypy 148 文件通过。
定向原件检查通过。最终计数与失败详情保存在
`output/knowledge-rebuild-20261017/pytest-final.xml` 及 `verification-final.json`。
原始 Windows 基线已有三个 POSIX 部署符号链接替换失败；UTF-8 运行避免主机 GBK 写入问题，
未为使检查变绿修改部署代码或弱化有效断言。

回滚演练只使用临时版本目录和临时指针，具体结果见
`output/knowledge-rebuild-20261017/rollback-drill.json`。真实旧快照、manifest 和活动指针未修改。
复现命令为 `.venv/Scripts/python.exe scripts/drill_knowledge_rollback.py`，18 项检查已连续两次通过。
后续上线必须以同一发行包同时携带结构化目录和匹配索引，记录旧发行包及其哈希；回滚时切回完整旧发行包。
不要单独将联合候选的 RAG 指针切换到旧结构化数据旁。生产发布与回滚命令仍沿用既有发行流程，
本轮没有执行上线、Git 提交、推送或合并。
