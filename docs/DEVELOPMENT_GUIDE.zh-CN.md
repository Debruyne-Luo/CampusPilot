# CampusPilot 开发与协作手册

本手册用于领任务、划定模块边界、交接和验收。先读 [产品范围](PRODUCT.md) 与
[架构及决策登记表](ARCHITECTURE.md)，实现时以 [接口草案](API_CONTRACT.md)、
[Skill 约定](SKILLS.md)、[安全边界](SECURITY.md) 和已批准的 [ADR](adr/README.md) 为依据。
工程代理遵守 [AGENTS](../AGENTS.md)；Muse 的独立 QA、DataOps 和安全／发布验证职责见 [OPS](../OPS.md)。

## 当前阶段与决策边界

- **CONFIRMED**：成都理工大学是首个试点；v1 是帮助用户完成校园任务的公共信息、只读助手。
  包括服务、政策、部门、公开联系方式、公开教师资料、地点、路线、分步指导及官方在线服务链接。
- **CONFIRMED**：一个主 Agent、模块化 Skill、模块化单体；模型可替换；会话状态归应用所有；
  Evidence、Trace、Risk/Permission 有明确边界。工程团队分工不等于产品内的多 Agent。
- **DEFERRED**：登录后个人数据、认证接入、提交、撤销、修改记录、支付、身份变更等真实写操作。
  展示官方服务链接不代表已替用户登录、办理或完成业务。
- Core Framework Skeleton 技术方案已 **CONFIRMED**，Skeleton 与 Phase 1 实现 PR 已合并；
  Muse 报告 golden eval 基线为 22/22 通过，固定于 `554d7cb1`，报告依据与待交接项见 [OPS](../OPS.md#review-and-release-workflow)。
  使用 Python 3.14.7、uv、Protocol、Pydantic 2、pytest、mypy strict、Ruff 和 CLI；状态与日志仅在内存中。
  运行命令见 [README](../README.md)，批准依据见 [ADR 0003](adr/0003-python-skeleton-toolchain.md)。
- 生产 Agent runtime、Web 框架、模型供应商、持久数据库及 GIS 供应商仍未选定。
  全部 **OPEN** 项及其他技术状态以 [架构登记表](ARCHITECTURE.md) 为准，不能把建议当作批准。
- **REJECTED FOR V1** 项不得借模块实现绕过。新增决定由 Tech Lead 批准后进入 ADR。
  来源优先级、适用范围和冲突处理以 [PRODUCT](PRODUCT.md) 为准；第三方数据不能悄悄覆盖学校官方信息。

## 团队责任矩阵

| 角色 | 主要职责 | 评审与交接责任 | 权限边界 |
| --- | --- | --- | --- |
| Product Owner / Tech Lead | 产品、架构、事实批准、最终 Review / Merge | 确认 Issue、跨模块变更、发布门槛和数据 `verified` 状态 | 保留最终评审与合并权；实际账号仍待确认 |
| 前端同学（Teammate） | Frontend & Product Experience，包括 UI/UX、地图交互 | 评审用户流程、前后端契约、可访问性 | 不在客户端代替后端授权或生成校园事实 |
| Codex + GPT-6 Astra | 主要实现、开发自测、契约维护 | 提供变更证据、修复缺陷、完成模块交接 | 不自行合并，不自行选择未批准技术 |
| Muse | Independent QA + DataOps + Security Validation / Release Gate；后续 Agent Red Team | 独立测试、浏览器来源复核，锁定 Tested Commit SHA，输出 PASS / FAIL 与 blocking / non-blocking findings | 不决定最终架构、不 Merge、不自行标记 `verified`，不修改核心生产代码来使测试通过 |
| ChatGPT | 架构、研究、规划、评估设计、技术评审 | 检查边界、评估方法及设计取舍 | 建议不等于产品或架构批准 |

上述角色职责为 **CONFIRMED**。Muse 对重要 PR 使用独立环境，除复现开发测试外，主动设计边界、
负面和对抗测试；发现 production bug 先报告，由 Codex 修复。Muse 可以整理 QA 测试、DataOps 工具
或测试脚本，但不得擅自重构 Agent Core。QA 结论只适用于锁定的 Tested Commit SHA，提交变化后需回归。

下面的具体模块任务分配是 **PROPOSED**，应在上述角色边界内由具体 Issue 确认。
“审：Tech Lead”表示人类评审与批准；ChatGPT、前端同学、Muse 可按职责参与技术评审。
每个模块都要通过 Muse 独立 QA，不能用开发自测替代。代码归属不意味着模块要独立部署。

## 模块工作卡

本节描述未来工作。每张卡都给出责任、禁区、上下游、契约、Skeleton 与后续范围、负责人、
评审、Muse 验证和完成条件。所有契约字段、状态值及运行语义仍为 **PROPOSED**，以
[API_CONTRACT](API_CONTRACT.md) 为唯一接口草案；这里不另设枚举或数据结构。
下列模块卡保留分阶段目标；Skeleton 的当前实现与限制以 ARCHITECTURE 的状态说明为准，
其余阶段不是执行授权。具体 Python 契约已实现，但不代表冻结未来 Web API。

### 1. API

- **职责／禁区**：校验输入、关联会话、输出稳定结果；不直接访问模型 SDK，不信任客户端自报权限。
- **上游／下游**：前端或获批的本地入口输入 → AgentHarness 请求、任务进展、Evidence 与错误结果。
- **契约**：请求标识、会话归属、进展、结果与错误见 API_CONTRACT；传输方式仍 OPEN。
- **Skeleton／后续**：只定义应用边界契约；默认不需要 HTTP 服务。后续经批准实现传输、流式更新和取消。
- **负责人／评审**：Codex；审：Tech Lead、前端同学，ChatGPT 参与契约评审。
- **Muse／完成**：验证非法输入、会话混用、错误可理解性；上下游能按同一契约独立接入即达到该 Issue 的完成条件。

### 2. Agent / Harness

- **职责／禁区**：理解目标、选择 Skill、组织有限步骤、检查结果；不直接访问数据库、GIS 或外部 API，不创建第二主 Agent。
- **上游／下游**：任务与上下文 → ModelProvider、SkillRegistry、ToolExecutor、SessionStore、TraceEvent 及任务结果。
- **契约**：AgentHarness 边界、预算、取消、失败和完成语义；生产调度机制仍 OPEN。
- **Skeleton／后续**：确定性假 AgentHarness 串联三个 mock，仅是测试替身；后续另行比较和批准真实运行时。
- **负责人／评审**：Codex；审：Tech Lead、ChatGPT。
- **Muse／完成**：验证执行有界、失败可见、拒绝不能绕过；离线脚本流程可复现且不宣称完成真实业务。

### 3. Model Provider

- **职责／禁区**：适配模型请求、响应、工具调用及能力差异；不保存权威任务状态，不授予工具权限。
- **上游／下游**：AgentHarness 的标准请求 → 规范化模型结果或错误；供应商对象留在适配器内部。
- **契约**：ModelProvider、能力声明与错误约定；不暴露供应商 SDK 类型到领域契约。
- **Skeleton／后续**：实现确定性假 Provider；后续在模型选择、数据处理和成本要求获批后接入真实供应商。
- **负责人／评审**：Codex；审：Tech Lead、ChatGPT。
- **Muse／完成**：验证正常、畸形与失败响应；替换测试适配器不改变领域层，Skeleton 无网络、密钥或真实模型调用。

### 4. Context / Session

- **职责／禁区**：维护任务进度、上下文和证据引用；模型摘要不能覆盖权威状态、批准或完成记录。
- **上游／下游**：用户输入与执行结果 → AgentHarness 上下文、会话视图及状态更新。
- **契约**：SessionStore；会话、任务、运行的区分及并发、取消、恢复规则见接口草案。
- **Skeleton／后续**：内存实现和会话隔离演示，不承诺重启恢复；后续批准存储方案后实现持久化及恢复。
- **负责人／评审**：Codex；审：Tech Lead、ChatGPT。
- **Muse／完成**：验证隔离、续接、上下文保留证据引用；重启丢失限制明确，不把未知结果当成功。

### 5. Skills

- **职责／禁区**：表达可复用领域流程、输入要求、完成条件和回退；不是独立 Agent，文字不能自授权限。
- **上游／下游**：任务和可用上下文 → 给主 Agent 的流程要求与所需 Tool 描述。
- **契约**：Skill 标识、版本、输入、结果、工具依赖、风险与完成条件，详见 SKILLS。
- **Skeleton／后续**：最小合成流程定义；后续基于批准的真实服务逐项加入，避免通用大而全流程。
- **负责人／评审**：Codex；审：Tech Lead、ChatGPT；Muse 用浏览器核对真实业务来源，Tech Lead 最终批准事实。
- **Muse／完成**：验证缺输入、工具失败和未达完成条件；Skill 可独立解释依赖和完成依据。

### 6. Skill Registry

- **职责／禁区**：保存经评审的静态 Skill 清单、版本和依赖；不动态下载或执行未受信任插件。
- **上游／下游**：受审 Skill 定义 → AgentHarness 可查询的能力目录。
- **契约**：SkillRegistry 的注册、查询、重复与未知标识行为；依赖必须可解析。
- **Skeleton／后续**：静态注册和错误检查；后续按需要增加检索与版本管理，动态插件机制没有获批。
- **负责人／评审**：Codex；审：Tech Lead、ChatGPT。
- **Muse／完成**：验证重复标识、未知工具和无效定义被明确拒绝；清单与运行可用能力一致。

### 7. Tools / Tool Executor

- **职责／禁区**：校验、鉴权、执行并返回结构化观察结果；不提供任意 SQL、脚本或无约束网络访问。
- **上游／下游**：AgentHarness 的 Tool 请求 → 对应能力结果、Evidence、失败及 TraceEvent。
- **契约**：ToolExecutor、Tool 输入输出、PermissionDecision；每次执行都经过权限边界。
- **Skeleton／后续**：mock `search_service`、`find_office`、`route_plan`；后续按批准契约接真实能力。
- **负责人／评审**：Codex；审：Tech Lead、ChatGPT。
- **Muse／完成**：验证非法输入、未知工具、拒绝和失败；拒绝时未执行，mock 结果明确为合成数据且有轨迹。

### 8. Retrieval / RAG

- **职责／禁区**：检索适用文档段落和引用；不把所有问题强制送进 RAG，不生成不存在的政策或引文。
- **上游／下游**：任务查询、适用条件与已发布文档 → 可核验段落、Evidence 或无结果。
- **契约**：文档版本、段落定位、适用性和冲突／缺失表达；共用 Evidence。
- **Skeleton／后续**：仅预留边界，不导入文档或搭建检索；Phase 2 依据语料评估选方案，向量技术未选定。
- **负责人／评审**：Codex 实现，Muse DataOps 管数据流程；审：Tech Lead、ChatGPT、指定来源审核人。
- **Muse／完成**：验证原文对应、适用性、无命中、冲突与过期；达到获批任务集的检索和引用标准。

### 9. Structured Campus Data / Directory

- **职责／禁区**：精确查询服务、部门、公开联系方式、公开教师及地点；不得推断或收集非公开个人信息。
- **上游／下游**：Tech Lead 批准来源后由 Codex 结构化的记录和查询条件 → 精确字段、来源、核验状态与未知结果。
- **契约**：稳定记录标识、字段含义、适用范围及 Evidence；存储引擎不属于已批准契约。
- **Skeleton／后续**：只使用明显合成的服务／办公室 fixture；Phase 1 建立批准的真实记录与更新流程。
- **负责人／评审**：Codex 结构化实现，Muse DataOps 采集候选来源并复核；Tech Lead 最终批准事实及 `verified` 状态。
- **Muse／完成**：验证字段准确、来源一致、同名消歧与缺失信息；记录可追溯且更新责任明确。

### 10. GIS / Routing

- **职责／禁区**：地点解析、路线及限制说明；不编造路径、开放入口、无障碍能力或替代服务政策。
- **上游／下游**：地点、获准使用的位置与已批准地图数据 → 路线、限制和来源，前端负责展示交互。
- **契约**：地点／路线请求结果、数据版本、适用约束、失败与未知情况；GIS 供应商仍 OPEN。
- **Skeleton／后续**：`route_plan` 仅返回合成路线 fixture，禁止用于导航；Phase 4 再接真实数据和计算。
- **负责人／评审**：Codex 能力实现、前端同学地图交互；审：Tech Lead、数据审核人。
- **Muse／完成**：验证无路、地点歧义、关闭／无障碍信息缺失；测试路线有依据且不作无证据保证。

### 11. External Integrations

- **职责／禁区**：适配批准的外部服务与错误；不越权访问，不将成功跳转视为业务办理成功。
- **上游／下游**：许可范围内的 Tool 请求与官方链接记录 → 规范化结果、Evidence、跳转信息或失败。
- **契约**：目的服务、允许操作、超时、错误与来源；第三方协议类型不得扩散到领域层。
- **Skeleton／后续**：仅记录边界，无真实 API；Phase 5 可接公共只读服务与官方链接，认证自动化仍 DEFERRED。
- **负责人／评审**：Codex；审：Tech Lead、前端同学，Muse 参与运维约束评审。
- **Muse／完成**：验证链接权威性、允许目标、故障与失效提示；功能没有隐藏登录、私有数据访问或写操作。

### 12. Future Actions

- **职责／禁区**：未来准备、执行、核对真实写操作；当前 v1 禁止启用实际提交、修改、撤销或支付。
- **上游／下游**：未来经授权的精确操作及审批 → 执行凭证、失败或待核对结果。
- **契约**：操作标识、载荷绑定、幂等与结果核对；细节 DEFERRED，不能由工具成功消息代替真实凭证。
- **Skeleton／后续**：只记禁区和保留边界，不实现可执行 Action；Phase 8 必须单独变更范围并批准。
- **负责人／评审**：未来 Codex 实现；审：Tech Lead、ChatGPT，Muse 参与安全与恢复评审。
- **Muse／完成**：Skeleton 验证真实写操作不可达；未来验证重复提交、过期批准和未知结果不被盲目重试。

### 13. Permission / Approval

- **职责／禁区**：由应用决定操作是否允许；模型、Skill、检索文本及客户端都不能授予权限。
- **上游／下游**：操作、风险、调用上下文与批准记录 → PermissionDecision 和可审计的决定。
- **契约**：允许／拒绝的表达及理由属 PROPOSED；未来批准需绑定操作者、目的、精确载荷和版本。
- **Skeleton／后续**：最小只读 mock 策略，未知风险拒绝；不执行审批后的写操作，后续才实现完整审批生命周期。
- **负责人／评审**：Codex；审：Tech Lead、ChatGPT，Muse 验证边界。
- **Muse／完成**：验证拒绝不触发工具、文字注入不改权限、决定有 Trace；不存在绕过 Executor 的执行路径。

### 14. Evidence / Provenance

- **职责／禁区**：表达资料来源、定位、适用性及核验状态；不将检索时间当更新时间，不让模型自证权威。
- **上游／下游**：Directory、RAG、GIS、集成和 DataOps → Agent、API、前端和评估可引用的 Evidence。
- **契约**：Evidence 草案见 API_CONTRACT；未知字段保持未知，合成数据与官方资料明确区分。
- **Skeleton／后续**：合成证据贯穿 mock 结果；后续接入真实来源版本、审核、冲突与过期规则。
- **负责人／评审**：Codex 契约、Muse DataOps 流程；审：Tech Lead、ChatGPT、指定来源审核人。
- **Muse／完成**：验证引用可定位、来源不丢失、合成标记保留；每项关键结果能追溯依据或明确无依据。

### 15. Trace / Observability

- **职责／禁区**：记录可观察执行、权限和错误；不收集内部思维链，不把秘密或个人原始内容写普通日志。
- **上游／下游**：Harness、Executor、权限和能力事件 → 可关联的执行轨迹及后续运维信号。
- **契约**：TraceEvent、关联标识、排序、脱敏及执行日志；持久性与保留策略仍 OPEN。
- **Skeleton／后续**：内存有序日志覆盖成功、拒绝和失败；后续批准持久化、访问、监控及保留策略。
- **负责人／评审**：Codex 实现，Muse 提供 QA 与安全验证的可观察性需求；审：Tech Lead、ChatGPT。
- **Muse／完成**：验证关联、顺序、失败可见及脱敏；可从结果追到相应调用而不泄漏敏感内容。

### 16. Evaluation

- **职责／禁区**：衡量任务成功、引用支持、能力选择和边界；不以演示流畅度替代正确性，不自行改变验收标准。
- **上游／下游**：获批场景、参考依据和运行结果 → 可比较报告、失败分类及改进建议。
- **契约**：用例输入、期望、评分依据、版本和评估限制；数值门槛由 Tech Lead 批准。
- **Skeleton／后续**：列出合成流程可检查结果；后续加入真实代表场景、模型对比和发布回归集。
- **负责人／评审**：ChatGPT 评估设计、Muse 独立执行、Codex 支持实现；审：Tech Lead。
- **Muse／完成**：验证评价可重现、参考资料有效、缺失与冲突被覆盖；报告足以支持已约定的验收判断。

### 17. Tests

- **职责／禁区**：检验契约和关键失败行为；不只复述实现，不依赖真实账号、秘密或不稳定生产请求。
- **上游／下游**：接口约定、Issue 验收和缺陷 → 自动或手动验证证据、可复现回归。
- **契约**：每项验证关联行为、预期和执行方式；测试工具及命令待批准后创建。
- **Skeleton／后续**：最小契约、Registry、权限、Trace、内存隔离测试；后续扩展集成和端到端验证。
- **负责人／评审**：Codex 开发测试、Muse 独立 QA；审：Tech Lead，相关模块负责人参与。
- **Muse／完成**：在独立环境复跑并主动设计边界、负面、对抗测试；锁定 Tested Commit SHA，输出 PASS / FAIL、blocking / non-blocking findings，缺陷经修复后回归。

### 18. Frontend

- **职责／禁区**：呈现步骤、来源、地点、路线和进展；不硬编码未核实校园事实，不替代后端权限检查。
- **上游／下游**：API 结果与 Evidence → 用户可理解的视图；用户选择、澄清和取消 → API。
- **契约**：共享 API_CONTRACT；区分运行结束、指导完成与真实业务完成。
- **Skeleton／后续**：仅评审交互与契约，不搭建前端；后续另行选择技术并实现移动端体验、地图和错误状态。
- **负责人／评审**：前端同学；审：Tech Lead，Codex 评审接入契约，Muse 评审可测试性。
- **Muse／完成**：验证小屏、键盘操作、加载／失败／无结果、来源可达与地图限制；用户能识别下一步及信息可信度。

### 19. DataOps

- **职责／禁区**：Muse 可在功能开发前用浏览器预采集官方公开资料，整理 Source Inventory 和候选事实；未经 Tech Lead 明确授权不得写入 `data/cdut` 正式数据集，不得自行标记 `verified`。
- **上游／下游**：官方公开来源 → 默认 `verification_status=needs_review` 的候选数据 → Tech Lead 审核来源后由 Codex 按正式契约结构化实现；预采集不等于正式 CampusPilot 数据。
- **契约**：记录并核对 URL、页面标题、发布单位、时间、字段证据、版本、适用范围、冲突和过期风险，参见 PRODUCT、OPS；缺失事实不推断。
- **Skeleton／后续**：继续检查 fixture 的 synthetic 标记；真实数据的浏览器采集和复核与 synthetic demo 隔离，后续刷新与撤回细则仍待批准。
- **负责人／评审**：Muse 采集和 Source Review / Data Verification，Codex 结构化实现；Tech Lead 批准来源并保留事实最终批准权。
- **Muse／完成**：PR 阶段再次用浏览器对照正式数据与官方来源，保留差异和风险证据；由 Tech Lead 最终决定是否 `verified`。

真实数据流程：Muse 浏览器采集／复核官方来源 → `needs_review` → Tech Lead 批准来源
→ Codex 结构化实现 → Muse 对照官网再次复核 → Tech Lead 决定是否 `verified`。
批准来源不自动升级核验状态，数据默认保持 `needs_review`。

### 20. DevOps / Release

- **职责／禁区**：运行准备、配置、发布验证和恢复；不默认引入容器、云平台或分布式基础设施，不自行发布。
- **上游／下游**：获审版本、配置要求和验证结果 → 可运行交接、发布建议及恢复说明。
- **契约**：环境前提、配置和秘密边界、验证／恢复步骤及发布门槛，详见 OPS。
- **Skeleton／后续**：获批后验证本地最小执行方式；无生产部署。后续单独批准托管、日志、备份和发布流程。
- **负责人／评审**：Muse 负责 Security Validation / Release Gate；部署执行负责人由具体 Issue 指定；审：Tech Lead，Codex 评审应用运行需求。
- **Muse／完成**：在声明的环境复跑，检查无秘密和隐含依赖；限制与命令可复现，发布决定由 Tech Lead 作出。

### 21. AI Security / Red Team

- **职责／禁区**：检验 prompt injection、RAG poisoning、tool abuse、permission bypass、data leakage 等风险；不在 QA 中悄悄改架构，不测试未授权外部目标。
- **上游／下游**：SECURITY 边界、允许测试范围与版本 → 可复现发现、严重度、缓解及回归建议。
- **契约**：威胁场景、测试边界、证据脱敏、缺陷升级与关闭规则；当前与未来控制必须分开记录。
- **Skeleton／后续**：只验证最小拒绝和输入信任边界，不建完整安全平台；Phase 7 再扩展系统化 Red Team。
- **负责人／评审**：Muse 后续 Red Team，Codex 修复，ChatGPT 支持设计；审：Tech Lead。
- **Muse／完成**：按批准范围验证，重要发现有复现和处置；不能把未执行测试或未来控制写成已生效保护。

## 开发阶段

以下是阶段路线图：Phase 0 已获批并完成本地实现；Issue #2 的 Phase 1 三事务范围已获批，
具体实现和来源限制见 [结构化数据说明](../data/cdut/README.md)。Phase 1 的其余覆盖和
Phase 2–8 仍为 **PROPOSED**，不是执行授权。
阶段顺序为 Phase 0–8；每个阶段由独立 Issue
约定范围和验收。评估、测试、安全边界与数据质量应从最早相关模块开始，Phase 6/7 是专项深化，
并不意味着此前可以跳过这些工作。Phase 8 超出当前只读 v1，需新的明确批准。

| 阶段 | 目标 | 主要工作 | 负责人 | 依赖 | 完成条件 |
| --- | --- | --- | --- | --- | --- |
| Phase 0：Core Framework Skeleton | 空但可执行的边界演示 | 类型契约、假 ModelProvider／AgentHarness、内存 SessionStore、静态 Registry、权限 Executor、合成 Evidence／Trace、三个 mock 和最小测试 | Codex；Muse 独立 QA | 单独批准 Skeleton 及其语言／工具／入口／契约范围 | 确定性离线执行、拒绝不执行、轨迹完整；无真实数据和外部服务 |
| Phase 1：Structured Campus Data | 公共结构化信息可查且可追溯 | 来源登记、字段和记录审核、服务／部门／公开教师／地点查询、更新规则 | Codex 结构化实现；Muse 浏览器采集／复核；Tech Lead 批准事实 | Phase 0；具体试点服务、来源、存储方案获批 | 指定查询正确，缺失不编造，每项关键字段有依据和维护责任 |
| Phase 2：Retrieval / RAG | 政策解释有适用原文支持 | 批准语料、解析检查、检索和引用、冲突与无结果处理；评估是否需要嵌入等技术 | Codex + Muse；ChatGPT 支持评估设计 | Phase 1；语料权限、检索方案和质量门槛 | 代表场景达到获批标准，原文可定位，过期及冲突可见 |
| Phase 3：Real LLM Agent | 主 Agent 能组合真实只读能力 | 比较并批准运行时和模型、接入 Provider、澄清、预算、失败回退和任务状态 | Codex；ChatGPT 设计评审，Muse QA | Phase 0–2；运行时 ADR、模型和数据处理规则获批 | 多步任务和失败场景达到门槛，权限与证据不受模型替换破坏 |
| Phase 4：Campus GIS | 提供有依据的地点和路线 | 批准地图／路线数据和供应商、约束表达、地图 UI、隐私与未知情况 | Codex + 前端同学；Muse QA/DataOps | Phase 3；数据许可、覆盖、位置处理和 GIS 选择 | 指定路线可验证，歧义与不可达有回退，未知无障碍条件不被保证 |
| Phase 5：Online Service Integration | 把用户引导至官方公共服务 | 经审核的官方深链接、必要的公共只读适配、错误和业务完成边界 | Codex + 前端同学；Muse 验证 | Phase 4；具体服务与集成范围获批 | 链接及结果有来源，失效可见；没有认证、个人数据或写入越界 |
| Phase 6：Evaluation / Ops | 形成可验收、可运维的版本 | 系统评估、回归、运行指标、数据刷新、恢复和发布验证 | Muse；Codex 修复，ChatGPT 评估设计 | Phase 5；环境、保留、运行目标和发布门槛获批 | 报告可复现，运维交接完整，Tech Lead 接受剩余风险；部署另行授权 |
| Phase 7：AI Security / Red Team | 验证 AI 与工具信任边界 | 授权范围内提示注入、来源污染、泄漏与权限绕过测试，修复回归 | Muse；Codex 修复，ChatGPT 支持 | Phase 6；测试范围、数据及处置门槛获批 | 发现可复现、处置可追踪，未解决风险经 Tech Lead 决定 |
| Phase 8：Authorized Actions | 仅执行被明确授权的真实操作 | 另行设计身份、逐项审批、幂等、结果核对、恢复和审计 | Codex；Muse QA/Red Team，Tech Lead 批准 | Phase 7；新产品范围及每种 Action、认证与安全要求获批 | 逐项通过批准绑定、重复／未知结果和恢复测试；未批准操作不可达 |

Skeleton 的具体顺序、验收、排除项及必须先做的技术选择见
[Skeleton 当前状态](ARCHITECTURE.md#core-framework-skeleton--implemented-locally)。
实际安装、运行及测试命令统一维护在 README，避免多处复制。

Issue #2 交接：真实查询由 CLI 直接经过 ToolExecutor 调用 Directory，使用本地 JSON；
不经过 Fake ModelProvider / Fake AgentHarness。Evidence 统一区分 SyntheticEvidence 与
SourceEvidence，FieldEvidence 关联具体字段。所有真实记录为 needs_review，来源权威与
核验状态分开。find_office 可以只返回部门和未知地点；不得用页脚地址补全。
研究生证明保留2023年试运行限制，2026年平台资料不能把这些规则升级为已核实。
人工提供并确认当前首页链接的校园卡指南为2024年8月第四版；票据限定2026–2027学年，
24小时条件不包含支付宝。Codex 开发者检查、Muse 独立 QA／浏览器来源复核与 Tech Lead 对事实及 `verified` 的最终批准分开。

## GitHub 协作流程

GitHub 是项目唯一事实记录源。聊天建议应转成 Issue、文档、评审或 ADR 才成为团队可追踪记录。
commit、push 和发布按具体任务授权；以下流程本身不授予权限，Muse 和 Codex 均不得自行 Merge。

1. **Issue**：写目标、允许／禁止修改范围、依赖、验收、负责人、评审人和 QA；先暴露 OPEN 决策。
2. **短期分支**：从核实的基线开始，范围对应 Issue；保留他人工作，不因文档中的目录建议创建空应用结构。
3. **Codex / teammate 实现**：按批准契约开发并自测；跨边界变化先更新受影响契约、通知上下游，必要时请求架构批准。
4. **Pull Request**：解释问题、实际变化、验证和限制，关联 Issue／ADR；没有执行的检查明确标为未执行。
5. **Muse 独立 QA / source verification**：重要 PR 在独立环境中验证并主动设计边界、负面、对抗测试；锁定 Tested Commit SHA，输出 PASS / FAIL 和 blocking / non-blocking findings；涉及真实数据时用浏览器复核官方来源。
6. **Codex 修复**：根据 findings 修复 production bug；涉及产品或架构的变化交 Tech Lead 决定，Muse 不修改核心生产代码来使测试通过。
7. **Muse regression**：验证修复和受影响行为，提交变化后记录新的 Tested Commit SHA 和 QA 结果。
8. **Tech Lead final review**：核对范围、产品效果、契约、QA、事实及残余风险；辅助评审和 QA 不替代最终人类 Review。
9. **Merge**：由 Tech Lead 作出最终决定并合并。

## 可复用模块交接模板

将下列内容复制到 Issue 或交接记录；不适用写明原因，未知项写 OPEN，不用空白掩盖阻塞。

```text
模块名称：
目标：
当前状态：（未开始／文档草案／已实现待验证等，附版本或 PR；不要混同架构决策标签）
上游输入：（调用方、数据、前置条件）
下游输出：（消费者、结果、失败与证据）
接口 / schemas：（权威文档、版本、变更兼容性；未批准字段标 PROPOSED）
依赖：（模块、已批准技术、外部条件及尚未解决的 OPEN 项）
允许修改范围：（文件或模块、允许动作）
禁止修改范围：（不可改模块、不可访问数据、不可执行动作）
数据来源：（官方来源、适用范围、许可、审核人；fixture 写明 synthetic）
已知问题：（复现、影响、回退和待决事项）
风险等级：（依据、影响对象及是否需要批准；未知时明确未知）
测试：（执行方式、环境、结果、证据、未执行项；不存在的命令不得虚构）
Tested Commit SHA：（Muse 实际独立验证并锁定的完整 SHA；提交变化后重新回归）
QA 结果：（PASS / FAIL；blocking / non-blocking findings，复现证据与回归情况）
验收标准：（可观察行为、失败路径、证据和完成判据）
相关 ADR / 文档：（链接；只有已批准决定进入 ADR）
负责人：
评审人：
QA 负责人：（默认由 Muse 独立承担，具体 Issue 确认）
```

交接完成意味着接手者可以依据这份记录继续工作、复现结果并判断边界；不意味着允许扩大范围。
