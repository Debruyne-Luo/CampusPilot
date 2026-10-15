# Principal Architect 审查地图

整理日期：2026-10-14（Asia/Shanghai）。本文件是审查导航与事实索引，不是架构审计结论或新架构决策。

## 1. 审查对象与证据层级

- 目标工作区：`D:/Projects/CampusPilot-integration`，分支 `feat/desktop-backend-integration`，读取时 HEAD 为 `a38842beea6afd8d4ca66a15e39ef0ea0d596531`。
- 已提交融合来源：后端 `3c0c395`、桌面 `f3dc8ed`，共同基线 `5fd207c`；融合历史和堆叠 PR 关系见 [INTEGRATION:8](../../INTEGRATION.zh-CN.md#L8) 与 [INTEGRATION:35](../../INTEGRATION.zh-CN.md#L35)。
- **当前工作树还含未提交实现。** 读取时有 15 个已跟踪文件改动，并有官方资料导入、服务入口、知识包及测试等未跟踪文件。HEAD 不足以重建本次完整审查对象；精确文件身份应以同目录的基线清单为准。
- **部署证据是存档。** [LIVE_BASELINE:3](../../LIVE_BASELINE.zh-CN.md#L3) 记录 2026-10-13 发布源码 `258ff205b73d6b2207d0234d26f04fcdec09134a`、发布包 `r-994da5858c65`；[INTEGRATION:3](../../INTEGRATION.zh-CN.md#L3) 记录融合版未合并、未部署。本次没有连接生产核实，不能把本地代码、知识指针或历史健康检查等同于当前生产状态。
- 本地图仅做静态只读核查；历史测试结果均注明来源，没有在此重新执行模型、地图、搜索、资料采集、付费评测或部署。

## 2. 建议阅读顺序

1. [AGENTS](../../../AGENTS.md)、[PRODUCT](../../PRODUCT.md)、[ADR 索引](../../adr/README.md)：明确公开信息、只读辅助、单主 Agent、权限与人类最终合并/发布边界。
2. [INTEGRATION](../../INTEGRATION.zh-CN.md)、[LIVE_BASELINE](../../LIVE_BASELINE.zh-CN.md)、[ADR 0006](../../adr/0006-online-evidence-and-user-images.md)：区分最新本地增量、线上存档与已批准能力。ADR 0006 明确替代 ADR 0005 的部分 Jev 限制。
3. [app/main.py:33](../../../backend/src/campuspilot/app/main.py#L33)、[app/factory.py:84](../../../backend/src/campuspilot/app/factory.py#L84)、[config.py:84](../../../backend/src/campuspilot/config.py#L84)：先理解装配和开关，再进入运行逻辑。
4. [routes_chat.py:36](../../../backend/src/campuspilot/app/routes_chat.py#L36)、[AgentRunner:825](../../../backend/src/campuspilot/agent/executor.py#L825)、[plan.py:51](../../../backend/src/campuspilot/agent/plan.py#L51)：沿用户请求追踪理解、计划、工具、补证、生成与校验。
5. [rag.py:196](../../../backend/src/campuspilot/rag.py#L196)、[tools/knowledge.py:59](../../../backend/src/campuspilot/tools/knowledge.py#L59)、[official_knowledge.py:459](../../../backend/src/campuspilot/official_knowledge.py#L459)、[service_links.py:158](../../../backend/src/campuspilot/service_links.py#L158)：检查知识供应链与本次 WIP。
6. 按本文测试地图读取契约和失败用例，最后读 [INTEGRATION_QA](../../INTEGRATION_QA.zh-CN.md)、[SERVICE_LINKS](../../SERVICE_LINKS.zh-CN.md) 与发布实现；不要先由旧报告给最新工作树下结论。

## 3. 入口与模块边界

| 边界 | 当前职责与关键入口 | 审查时需保持的区分 |
| --- | --- | --- |
| 运行入口/装配 | [web.py:8](../../../backend/src/campuspilot/web.py#L8) 保留旧导入入口；[app/main.py:33](../../../backend/src/campuspilot/app/main.py#L33) 统一从 Settings 装配；[factory.py:128](../../../backend/src/campuspilot/app/factory.py#L128) 构建快照，:191 构建规则运行时，:225 构建 Agent | `legacy`、`phase1`、`phase2` 和 Agent 开关组成不同执行路径；默认配置不能代表部署配置 |
| Core 合约 | [evidence.py:12](../../../backend/src/campuspilot/evidence.py#L12)、[domain.py:14](../../../backend/src/campuspilot/domain.py#L14)、[contracts.py:130](../../../backend/src/campuspilot/contracts.py#L130)、[interfaces.py:24](../../../backend/src/campuspilot/interfaces.py#L24) | 仓库没有独立 `core/` 目录；这些根模块承载领域、证据、权限、运行合约；不要把所有模块根文件当作同一种运行路径 |
| Agent | [understand.py](../../../backend/src/campuspilot/agent/understand.py)、[plan.py:51](../../../backend/src/campuspilot/agent/plan.py#L51)、[executor.py:196](../../../backend/src/campuspilot/agent/executor.py#L196)、[verify.py:52](../../../backend/src/campuspilot/agent/verify.py#L52) | 一个主 Agent；计划由代码形成，模型可追加受白名单限制的工具调用；旧 [skeleton.py](../../../backend/src/campuspilot/agent/skeleton.py) 是独立合成演示 |
| 模型/嵌入 | [llm/chat_model.py:114](../../../backend/src/campuspilot/llm/chat_model.py#L114)、[:167](../../../backend/src/campuspilot/llm/chat_model.py#L167)、[:264](../../../backend/src/campuspilot/llm/chat_model.py#L264) 提供生成与工具调用协议/适配；[embedding.py:49](../../../backend/src/campuspilot/llm/embedding.py#L49) 提供 Cloudflare 嵌入 | 生产适配器与 [interfaces.py:24](../../../backend/src/campuspilot/interfaces.py#L24) 的合成 ModelProvider 是两套接口，不能推定彼此覆盖 |
| 检索/证据 | [rag.py:196](../../../backend/src/campuspilot/rag.py#L196) 读快照；[bm25.py:93](../../../backend/src/campuspilot/retrieval/bm25.py#L93) 做适用性过滤；[hybrid.py:140](../../../backend/src/campuspilot/retrieval/hybrid.py#L140) 融合；[grounding.py:97](../../../backend/src/campuspilot/retrieval/grounding.py#L97) 判断支持程度 | `knowledge.json` 的旧确定性资料查询与 RAG 快照并存；向量缺失/失败会显式降级，grounding 的 `flag` 与 `block` 行为不同 |
| 结构化目录 | [directory/repository.py:102](../../../backend/src/campuspilot/directory/repository.py#L102) 从明确 JSON 文件加载和校验；[:128](../../../backend/src/campuspilot/directory/repository.py#L128) 起查询事务、办公室、地点与教师 | 结构化数据、来源状态、坐标和 RAG 正文分开；供应商 POI 不写回正式目录 |
| 工具边界 | [tools/base.py:43](../../../backend/src/campuspilot/tools/base.py#L43) 为 Agent 白名单与参数校验；[tools/__init__.py:63](../../../backend/src/campuspilot/tools/__init__.py#L63) 装配 Agent 工具；[tools/executor.py:51](../../../backend/src/campuspilot/tools/executor.py#L51) 为原合约式权限/日志执行器 | 当前 Agent 的 ToolRegistry 路径与旧 ToolExecutor 路径不同，审查应分别追踪授权、输出校验、日志和错误语义 |
| API/会话 | [api.py:71](../../../backend/src/campuspilot/api.py#L71) 提供 Bearer 工具 API；[app/state.py:106](../../../backend/src/campuspilot/app/state.py#L106) 保存浏览器状态；[routes_chat.py:36](../../../backend/src/campuspilot/app/routes_chat.py#L36)、[routes_data.py:15](../../../backend/src/campuspilot/app/routes_data.py#L15) 提供同源页面 API | Bearer 工具 API、浏览器匿名会话与反向代理访问门禁是不同边界；会话/并发/预算以单进程为基础 |
| 联网/图片/地点 | [web_evidence.py:600](../../../backend/src/campuspilot/web_evidence.py#L600)、[attachments.py:103](../../../backend/src/campuspilot/attachments.py#L103)、[places_discovery.py:101](../../../backend/src/campuspilot/places_discovery.py#L101) | 官网事实、第三方线索、用户图片观察和地图 `location_only` 证据必须保留不同权威；见 ADR 0006 |
| 前端 | [v2/main.mjs:1](../../../backend/src/campuspilot/web_assets/v2/main.mjs#L1) 装配聊天、附件、桌面、地图、清单；[sse.mjs:23](../../../backend/src/campuspilot/web_assets/v2/sse.mjs#L23) POST 流/普通回退；[map.mjs](../../../backend/src/campuspilot/web_assets/v2/map.mjs)、[map-frame.js](../../../backend/src/campuspilot/web_assets/map-frame.js)、[guidance.js](../../../backend/src/campuspilot/web_assets/guidance.js) 管地图/前台引导 | v2 是默认页面；classic/地图 iframe 仍保留。浏览器持久清单、暂态定位、后端会话和模型上下文具有不同生命周期 |
| 离线维护/发布 | [official_knowledge.py:459](../../../backend/src/campuspilot/official_knowledge.py#L459)、[knowledge_release.py:381](../../../backend/src/campuspilot/knowledge_release.py#L381) 管知识候选/发布；[deploy/_release.py:50](../../../deploy/_release.py#L50)、[:142](../../../deploy/_release.py#L142) 管整包/切换/回滚 | 本地知识 `current.json` 的切换与生产整包发布是不同操作；维护脚本具有写文件/潜在网络副作用，静态审计不需运行它们 |

## 4. 五条关键调用链

### A. 文本问答：浏览器到已校验答案

`v2/main.mjs submit` → [sse.ask:23](../../../backend/src/campuspilot/web_assets/v2/sse.mjs#L23) → [POST /api/chat/stream:65](../../../backend/src/campuspilot/app/routes_chat.py#L65) → [session_for:149](../../../backend/src/campuspilot/app/state.py#L149) / 会话 busy / ChatBudget → [AgentRunner.run:825](../../../backend/src/campuspilot/agent/executor.py#L825) → [understand:892](../../../backend/src/campuspilot/agent/executor.py#L892) → [make_plan:999](../../../backend/src/campuspilot/agent/executor.py#L999) → [_run_plan:501](../../../backend/src/campuspilot/agent/executor.py#L501) → [_call:281](../../../backend/src/campuspilot/agent/executor.py#L281) → [ToolRegistry.call:64](../../../backend/src/campuspilot/tools/base.py#L64) → 目录/知识/清单工具 → [_compose:1528](../../../backend/src/campuspilot/agent/executor.py#L1528) / verify_answer → 最终响应。

事实：SSE `answer_delta` 在完成答案校验后分段发出，见 [routes_chat:121](../../../backend/src/campuspilot/app/routes_chat.py#L121)；流取消会取消工作任务并释放 claim，见 [:132](../../../backend/src/campuspilot/app/routes_chat.py#L132)。普通 `/api/chat` 在 Agent 未启用时走 ChatRuntime 或旧本地/Dify 路径，见 [:38](../../../backend/src/campuspilot/app/routes_chat.py#L38)。应分别验证这些路径的契约，不能用某条路径的测试代表所有运行模式。

### B. RAG 与官方办事入口（包含 WIP）

[HybridKnowledgeTool.run:59](../../../backend/src/campuspilot/tools/knowledge.py#L59) → [SnapshotStore.acquire:230](../../../backend/src/campuspilot/rag.py#L230) → 指针/快照/manifest/索引校验 → [HybridRetriever:140](../../../backend/src/campuspilot/retrieval/hybrid.py#L140) → 适用性过滤与 BM25/向量/RRF → grounding → hit 的来源、定位、哈希、版本及 `service_links` → Agent 校验实际引用 → [answer_service_links:293](../../../backend/src/campuspilot/service_links.py#L293) → [render.serviceLinksCard:51](../../../backend/src/campuspilot/web_assets/v2/render.mjs#L51)。

事实：入口目的 URL 由程序从版本绑定的已采用材料解析；不是由模型构造。[service_links:297](../../../backend/src/campuspilot/service_links.py#L297) 要求 success/limited、实际引用、非明确 ungrounded、非 web/stale，并核对源 ID/URL 与审核状态；前后端另做 URL 约束。[SERVICE_LINKS:24](../../SERVICE_LINKS.zh-CN.md#L24) 明确 `availability=not_checked`，来源核对日期不是实时可达性证明。

### C. 用户图片与跨轮状态

[attachments.mjs:17](../../../backend/src/campuspilot/web_assets/v2/attachments.mjs#L17) → [POST /api/attachments:14](../../../backend/src/campuspilot/app/routes_attachments.py#L14) → [normalize_image:52](../../../backend/src/campuspilot/attachments.py#L52) → AttachmentStore（按 user、TTL、容量保存）→ 聊天仅传 attachment IDs → [routes_chat._images_for_turn:248](../../../backend/src/campuspilot/app/routes_chat.py#L248) → [AgentRunner.run:825](../../../backend/src/campuspilot/agent/executor.py#L825) / 图像任务上下文 → [llm.user_content:40](../../../backend/src/campuspilot/llm/chat_model.py#L40) → 模型观察或原文阅读 → 答案校验。

事实：模型观察带 `authority=user_observation`，见 [executor:895](../../../backend/src/campuspilot/agent/executor.py#L895)。读取附件仍校验会话所有权，见 [routes_attachments:58](../../../backend/src/campuspilot/app/routes_attachments.py#L58)；后台清理及关闭见 [factory:270](../../../backend/src/campuspilot/app/factory.py#L270)。应审查图片观察、历史回答、官方事实与导航目的地之间的升权阻断。

### D. 统一地点查询到地图引导

地图 [place-search.mjs:7](../../../backend/src/campuspilot/web_assets/v2/place-search.mjs#L7) → [POST /api/places/search:57](../../../backend/src/campuspilot/app/routes_data.py#L57)；聊天工具 [PlaceDiscoveryTool:37](../../../backend/src/campuspilot/tools/directory.py#L37) → 同一 [PlaceDiscovery.search:120](../../../backend/src/campuspilot/places_discovery.py#L120) → 正式目录精确名称/别名/教室 → 可选高德 Web 服务 → 临时 MapCandidate → 用户明确选择/点击路线 → 原地图 Walking 与 guidance。

事实：临时 POI 独立类型声明 `GCJ02`、`location_only`、`transient`、`exact/candidate`，见 [places_discovery:38](../../../backend/src/campuspilot/places_discovery.py#L38)。装配仅在 `amap_discovery` 开启后给地图与 Agent 注入同一服务，见 [factory:244](../../../backend/src/campuspilot/app/factory.py#L244)。来源限制与导航成功、实地可走性仍需分别核查。

### E. 离线官方资料发现、采纳和恢复（WIP）

用户保存公开栏目 HTML → [official_discovery.discover:191](../../../scripts/official_discovery.py#L191) 只提取实际 href/分页线索 → [import_browser_exports:446](../../../scripts/import_browser_exports.py#L446) 导入已保存指南正文/附件 → [official_knowledge.extract:278](../../../backend/src/campuspilot/official_knowledge.py#L278) 输出候选段落 → 人工/程序显式条款、适用性、日期证据 → [official_knowledge.build:459](../../../backend/src/campuspilot/official_knowledge.py#L459) 稳定条款 upsert 与 provenance → [write_candidate:183](../../../backend/src/campuspilot/knowledge_release.py#L183) / 索引绑定 → [publish:381](../../../backend/src/campuspilot/knowledge_release.py#L381) → `versions/<version>/`、`current.json`、`last_good.json` → SnapshotStore 运行时读取。

事实：栏目发现不代表正文已采集或资料已采用，见 [OFFICIAL_DISCOVERY:26](../../OFFICIAL_DISCOVERY.zh-CN.md#L26)；失败文档保留上次成功数据，版本关系与原始字节进 provenance，见 [official_knowledge:459](../../../backend/src/campuspilot/official_knowledge.py#L459)。当前 SnapshotStore 支持已校验 last_good 冷恢复，见 [rag:230](../../../backend/src/campuspilot/rag.py#L230)。需按知识版本核验资料和索引，不可只看目录名或 source 数量。

## 5. 数据流、信任边界与生命周期

| 输入/状态 | 当前经过的边界 | 审查要点 |
| --- | --- | --- |
| 浏览器 message、附件引用 | [ChatInput](../../../backend/src/campuspilot/app/validation.py#L13)、[同源检查](../../../backend/src/campuspilot/app/state.py#L124)、[请求体限制](../../../backend/src/campuspilot/app/factory.py#L313)、匿名 cookie 会话 | 跨会话访问、并发写入、断连取消、重置与 TTL；同源检查不等于学校账号身份认证 |
| 用户问题送嵌入/模型 | [public_input](../../../backend/src/campuspilot/chat_runtime.py#L97)、[routes_chat:46](../../../backend/src/campuspilot/app/routes_chat.py#L46)、[AgentRunner:835](../../../backend/src/campuspilot/agent/executor.py#L835) | 区分规则过滤已有覆盖与未验证隐私风险；不能由静态过滤存在推定所有敏感输入都会被识别 |
| 本地目录 JSON 与快照 | DirectoryRepository、typed contracts、字段来源覆盖；快照/manifest/raw/index 哈希及版本绑定 | `needs_review`、`official_document`、`verified` 不互相等价；`official_document` 不代表实地核验；资料适用性与采集日期分开 |
| 模型/工具输出 | 工具白名单、Pydantic 参数、已允许证据 ID、[verify_answer](../../../backend/src/campuspilot/agent/verify.py#L52)、grounding | 生产 Agent 与旧权限执行器分别验；模型不能授予权限、创建正式事实、目的 URL 或已完成业务状态 |
| 搜索来源与网页正文 | [WebEvidenceService](../../../backend/src/campuspilot/web_evidence.py#L600)、[SafePageReader](../../../backend/src/campuspilot/web_evidence.py#L510)、[public_url](../../../backend/src/campuspilot/web_evidence.py#L412)、共享 OnlineBudget | URL/DNS/重定向、正文大小和截止时间、供应商摘要与原始正文的区分；第三方来源不自动成为学校事实 |
| Jev 决策 | [executor._with_web](../../../backend/src/campuspilot/agent/executor.py#L1234)、[jev_plugin.py](../../../backend/src/campuspilot/jev_plugin.py)、ADR 0006 | off/shadow/on 有不同权限；在线补证前后各一次的约束与故障语义；判断不得提高来源权威或绕过预算 |
| 图片文件 | 格式/解码/像素与原始大小限制、去元数据、临时目录、按 user 访问 | 一小时固定匿名会话、新对话/重启清理；模型读取图片是外部处理边界，原图不得进入知识包、普通日志或持久清单 |
| 地图/GPS 与清单 | 浏览器地图 iframe/消息、坐标体系、前台 guidance；[handling-store](../../../backend/src/campuspilot/web_assets/v2/handling-store.mjs)、[checklist-store](../../../backend/src/campuspilot/web_assets/v2/checklist-store.mjs) | 个人位置按批准方向留浏览器；后端 query 不应包含位置；本地持久清单与服务端会话清理具有不同语义 |
| 发布与主机状态 | [systemd:12](../../../deploy/campuspilot.release.service#L12)、[Caddy:6](../../../deploy/Caddyfile.release#L6)、[release install](../../../deploy/_release.py#L142) | 单 worker、匿名内存状态、可写预算目录、不可变发布、健康检查和回滚；配置文件声明不等于生产实际配置 |

## 6. 测试与验收证据地图

| 关注面 | 定位 |
| --- | --- |
| Core/旧工具权限、日志、合成状态 | [test_skeleton.py](../../../tests/test_skeleton.py)、[test_directory.py](../../../tests/test_directory.py)、[test_api.py](../../../tests/test_api.py)、[test_p1_foundation.py](../../../tests/test_p1_foundation.py) |
| Agent/普通与流式问答、图片追问 | [test_agent_loop.py](../../../tests/test_agent_loop.py)、[test_backend_evidence_flow.py](../../../tests/test_backend_evidence_flow.py)、[test_image_followup.py](../../../tests/test_image_followup.py)、[test_attachments.py](../../../tests/test_attachments.py)、[test_web.py](../../../tests/test_web.py) |
| 检索、依据判断、Jev/联网边界 | [test_hybrid_retrieval.py](../../../tests/test_hybrid_retrieval.py)、[test_grounding_refusal.py](../../../tests/test_grounding_refusal.py)、[test_jev_plugin.py](../../../tests/test_jev_plugin.py)、[test_web_evidence.py](../../../tests/test_web_evidence.py) |
| 知识发布/WIP官方导入/服务链接 | [test_knowledge_release.py](../../../tests/test_knowledge_release.py)、[test_snapshot_fallback.py](../../../tests/test_snapshot_fallback.py)、[test_official_knowledge.py](../../../tests/test_official_knowledge.py)、[test_browser_exports.py](../../../tests/test_browser_exports.py)、[test_official_discovery.py](../../../tests/test_official_discovery.py)、[test_service_links.py](../../../tests/test_service_links.py) |
| 地点/地图/浏览器模块 | [test_places_discovery.py](../../../tests/test_places_discovery.py)、[test_map_ux.py](../../../tests/test_map_ux.py)、[v2_evidence_media.test.mjs](../../../tests/v2_evidence_media.test.mjs)、[v2_service_links.test.mjs](../../../tests/v2_service_links.test.mjs)、其他 `tests/*.test.mjs`/`*.test.js` |
| 发布/运行迁移与质量门禁 | [test_release.py](../../../tests/test_release.py)、[test_runtime_migration.py](../../../tests/test_runtime_migration.py)、[test_migration_gate.py](../../../tests/test_migration_gate.py)、[evaluation/runtime-migration/README](../../../evaluation/runtime-migration/README.md) |

工具配置见 [pyproject:38](../../../pyproject.toml#L38)（pytest）、[:42](../../../pyproject.toml#L42)（strict mypy）、[:60](../../../pyproject.toml#L60)（Ruff）；Node 用内建测试运行器。维护依赖组新增 `pypdf`，见 [:12](../../../pyproject.toml#L12)。测试样题、知识原始字节和批准哈希受行尾影响，不能通过重写预期绕过一致性校验。

历史证据必须按截面阅读：

- 固定融合源码 `893abcb`：文档报告标准 Git 字节下 pytest **618 passed / 3 failed**、Node **64 passed**、Ruff/mypy 通过；三项失败是 Windows POSIX 发布切换，见 [INTEGRATION:54](../../INTEGRATION.zh-CN.md#L54) 和 [QA:75](../../INTEGRATION_QA.zh-CN.md#L75)。本地图没有复跑，且该结果不覆盖最新 WIP。
- [INTEGRATION_QA:15](../../INTEGRATION_QA.zh-CN.md#L15) 明确审查者实现过部分模块；230 项针对性检查中的独立性范围不可扩大。
- 未提交服务链接截面由 [SERVICE_LINKS:49](../../SERVICE_LINKS.zh-CN.md#L49) 报告 pytest **784 passed / 3 failed**、Node **70 passed**；普通/SSE 与浏览器场景用了真实知识和脚本化模型，不能称真实 DeepSeek 生成验收。
- `.github` 目前只有模板与占位 CODEOWNERS，没有 Actions 工作流；[CODEOWNERS:1](../../../.github/CODEOWNERS#L1) 不配置实际所有者，不证明分支保护、必需检查或 Merge 权限已强制执行。

## 7. 文档漂移与 WIP 限制

| 已见事实 | 对审查的影响 |
| --- | --- |
| [ARCHITECTURE:3](../../ARCHITECTURE.md#L3) 顶部仍记 10-12 的 `31ed5bb`/`r-0f1805acf68e`；LIVE_BASELINE 顶部已是 10-13 | 权威文档中混有历史截面；最新部署事实从基线顶部及清单读取，且仍只是存档 |
| [ADR 0005:25](../../adr/0005-backend-runtime-and-knowledge-publication.md#L25) 只许 Jev 影子；[ADR 0006:11](../../adr/0006-online-evidence-and-user-images.md#L11) 已批准在线补证判断，并在 :22 明确替代 | 不能以旧 ADR 或历史描述否定已批准增量，也不能把批准视为质量已达标 |
| [pyproject:4](../../../pyproject.toml#L4) 描述仍为 offline synthetic skeleton；README 与旧 CLI 保留历史路径 | 先从 app 装配识别真实生产候选路径；合成演示的权限/状态测试不能自动推广到 AgentRunner |
| 本地 `data/cdut/rag/current.json` 为 `kb-229ee34eba99ef34`；`last_good.json` 为 `kb-f08fa4fd8b583700`；SERVICE_LINKS 记 176 来源/322 片段 | 这是本地 WIP 知识状态，不是部署升级；审查时连同 raw、manifest、索引和指针一起冻结；不能只锁代码 HEAD |
| WIP 同时修改 rag/knowledge_release/tools/Agent 和少量前端，新增 official ingestion/discovery/service links 与测试 | 已提交融合版和 WIP 应分开评估增量风险；最终架构审计需覆盖未跟踪代码，不以 `git diff HEAD` 的已跟踪输出作为完整清单 |
| 文档记录的 mock/脚本化模型、真实接口冒烟、浏览器 viewport、真机/现场步行是不同证据 | 95% 独立保留集、真实图片/联网正文与现场导航等未验边界以各报告原限定为准，不能互相补齐 |

## 8. 高价值审查问题（尚未形成结论）

1. **主 Agent 的复杂性是否被充分隔离？** 从 `AgentRunner` 的图像任务、目录规则、工具循环、联网判断、Jev、答案校验与响应装配，评估哪些责任需要更深的模块接口；先给出耦合和失败传播证据，再提出最小改动建议。
2. **两套工具路径是否兑现同一权限承诺？** 对照 ToolRegistry 和 ToolExecutor 的可调用范围、参数/输出契约、证据、日志与错误语义，明确哪些是历史兼容、哪些是当前安全边界，避免只因名称相似推定一致。
3. **配置组合是否可解释且可验证？** 检查 legacy/phase1/phase2、Agent、检索、grounding、Jev、搜索、图片、高德发现与知识指针的合法组合；启动错误、降级结果与 UI 能力声明是否一致。
4. **数据供应链是否保持证据与版本闭合？** 检查条款稳定 ID、原始 DOM/附件、当前 revision、显式日期/适用性、索引、服务入口、发布锁和冷恢复；追踪坏包、部分失败、历史材料和并发切换下的可观察行为。
5. **一个请求是否始终使用预期知识版本？** SnapshotStore 的单次 acquire 保持一个 retriever；继续检查同一 Agent 轮次多次工具调用与发布并发时是否需要更强的一致性约定，不由注释替代调用链证据。
6. **会话和预算的生命周期是否适配部署约束？** 单 worker 与内存会话是当前事实；审查并发、流取消、reset、附件到期、后台任务、进程重启及发布切换的失败行为，区分已批准约束与未来扩展需求。
7. **质量证据能否支撑产品承诺？** 将资料缺失、检索漏召回、适用性错误、生成错误、误拒与实际路线错误分别归因；历史通过率、合成 API 回归与真实用户任务通过率需要独立标签和固定版本。

以上为审查入口与待验证假设。本文件不授权修改核心代码、安装依赖、请求外部模型、采集新资料、提交、推送、合并或部署。
