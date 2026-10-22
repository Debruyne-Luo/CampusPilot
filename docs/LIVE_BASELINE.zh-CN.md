# 当前线上版本基线

## 2026-10-21 完整线上核对

核对时间：2026-10-21 22:53:17（America/Los_Angeles），即 `2026-10-22T05:53:17Z`。
文件名中的 `20261022` 使用原始 UTC 证据日期，不能据此误读为洛杉矶次日。
本次只读读取服务器发布清单并重新计算全部文件哈希，没有修改配置、文件或服务。

| 项目 | 核对结果 |
| --- | --- |
| 用户入口 | <https://cdutdino.pages.dev/> |
| 源码提交 | `0f982edb2cc57d33bee9542c5c14b3031a775633` |
| 整合分支 | `feat/harness-jev-submission-20261020`；[PR #38](https://github.com/Debruyne-Luo/CampusPilot/pull/38) 未合并 |
| 发布目录 | `/opt/campuspilot/releases/r-9431bf8d5c80` |
| 发布文件 | 623 个文件 SHA-256 逐项一致，0 个哈希错误 |
| 前端资源 ID | `ea0e123f8db8`；源码 ZIP 中前端与实际页面引用相符 |
| 知识版本 | `kb-1d15bf97b31c0d90`（192 来源、402 片段） |
| 知识恢复版本 | `kb-229ee34eba99ef34` |
| 服务 | `campuspilot`、`campuspilot-gateway`、`nginx`、`x-ui` 均为 active |
| GitHub 长期主线 | 本轮开始时 `origin/main` 为 `01d5318`；线上不等于当前 GitHub main |

原始发布文件清单见 [live-20261022.manifest.json](releases/live-20261022.manifest.json)。
非敏感运行配置、服务状态和逐项检查结果保留在本地交付证据
`output/submission-closeout-20261022/live-audit.json`；未导出完整环境、凭据或生产对话。
这次检查补足了此前仅核对源码 ZIP/前端的证据，确认完整后端发布身份；
文件匹配和服务 active 不等于每项业务、模型回答、实际地图路线均正确。

### 运行配置

以下来自活动服务的显式环境，区别于源码默认及无密钥模板：

| 变量 | 生效值 |
| --- | --- |
| `CAMPUSPILOT_RUNTIME_MODE` | `phase2` |
| `CAMPUSPILOT_AGENT_LOOP` | `on` |
| `CAMPUSPILOT_RETRIEVAL_MODE` | `lexical` |
| `CAMPUSPILOT_MODEL` | `deepseek-flash` |
| `CAMPUSPILOT_GROUNDING` | `flag` |
| `CAMPUSPILOT_JEV` / `CAMPUSPILOT_JEV_ROUTING` | `on` / `on` |
| `CAMPUSPILOT_IMAGES` | `on` |
| `CAMPUSPILOT_ASSET_VERSION` | `auto` |
| `CAMPUSPILOT_HARNESS_PROFILE` | 空，未采用实验 profile |
| `PUBLIC_ORIGIN` | `https://campuspilot.38-244-61-184.sslip.io:8443` |

图片理解使用独立 reader，文本回答与图片能力分别验证。Search/Fetch 是按需只读能力；
本次白名单配置快照未捕获其全部配置，不能由此推断每家外部服务的即时可用性或价格。
模型名是供应商别名，不锁定供应商内部权重；后续同名模型的回答可能改变。

### 验证状态与提交候选

此前最新固定回答验收为 **55/60**，自动检查记录为 Linux Python **1183 项**、Node **105 项**；
这些是已有版本的证据，本轮不把它们重新标记为修复后的通过结果。旧 `57/60`、`54/60`
是不同源码/提示词及执行阶段的报告，原文继续保留，不能合并为同一次验收。

本轮以此线上版本为基线收尾，针对 `kq-037/039/076/079/112` 复验；
完整过程、工作区清单和交付要求见 [提交版收尾](SUBMISSION_CLOSEOUT.zh-CN.md)。
候选代码与线上代码分别固定身份；本轮不直接合并 PR 或切换生产，既有 Release 不变。

真实手机 Safari/微信、实际 GPS 和低端设备验收仍未被此次文件核对覆盖；
固定 RAG 验收与 Search/Fetch、图片、地图联调分别记录。24 小时观察须对应真实切换时间，
不能因自动化存在就声称观察完整。评审结束日期仍未提供，未宣称已覆盖整个评审期。

## 历史记录阅读方式

以下内容保留当时的提交、配置、失败和测试结论；“当前”“本次”“未上线”和 526 均指该阶段。
它们不覆盖页首的实际线上身份，不作为再次初始化或删除历史工作区的依据。

2026-10-21迁移核对：原`cdutdino.pages.dev`返回526，旧服务器未找到原应用目录或活动服务。
以下历史清单不构成健康回滚目标。新机整合、验收与剩余门槛见
[本轮发布交接](qa/release-20261021.md)；正式切换后以PR/发布清单记录的提交和包身份为准。

## 2026-10-15 历史核对记录（非当前部署）

核对日期：2026-10-15（Asia/Shanghai）。用户批准发布整合后的集成分支，不合并 main。

| 项目 | 当前结果 |
| --- | --- |
| 用户入口 | https://cdutdino.pages.dev/ |
| 源码提交 | `eba182cce42aa8ff506a04aa3738cdf5ced818d6` |
| 分支 | `main`（整合已回到主干） |
| 发布目录 | `/opt/campuspilot/releases/r-62d8e21843ee` |
| 知识包 | `approved-20261011b` / `kb-f08fa4fd8b583700`（未改） |
| 回滚目标 | `/opt/campuspilot/releases/r-869cfdc79a57` |

当前线上包含 Teal 玻璃主题前端、架构审查修正、图片证据后端、桌面交互、办理清单、
GPS 引导坐标转换修复，以及**图片理解**与高德在线地点搜索。图片理解由独立读图模型
提供（`gemini-3.5-flash-lite`），文本答题仍使用 `deepseek-flash`。本轮发布的细节见
[图片理解发布记录](releases/image-reader-20261015.md)、
[GPS 修复发布记录](releases/gpsfix-20261015.md) 与
[集成发布记录](releases/integration-20261015.md)。

真实手机 Safari／微信、实际 GPS 路线与 3D 引导仍未验收。
`python scripts/check_live_baseline.py` 默认对照发布清单；此离线检查不证明服务器仍运行该版本。
下方记录只保留为历史证据，其版本、测试结论和清理约束不应覆盖本次发布。

## 2026-10-12 历史核对记录（非当前部署）

核对日期：2026-10-12（Asia/Shanghai）。用户要求以当前上线版本整理仓库。
此记录描述实际部署与本地代码对应关系，不新增架构决策，也不宣布验收通过。

### 版本身份与证据

| 项目 | 核对结果 |
| --- | --- |
| 用户访问入口 | https://cdutdino.pages.dev/ |
| 源码提交 | `31ed5bb0264d927c7918046b66b2947c013e8205` |
| 部署目录 | `/opt/campuspilot/releases/r-0f1805acf68e` |
| current 指向 | 上述不可变发布目录 |
| 发布包 ID | `r-0f1805acf68e` |
| 前端资源 ID | `a44289c47acf`（实际首页引用） |
| 知识包 | `approved-20261011b` |
| 知识版本 | `kb-f08fa4fd8b583700` |
| 进程入口 | `campuspilot.web:app_factory`，单 worker，服务 active |

只读读取服务器 `MANIFEST.json`，120 个文件逐项 SHA-256 均一致；进一步读取上述提交的
Git blob，120 项均与部署清单一致。本地工作树也逐项核对，91 个文本文件仅有 Windows
CRLF/LF 差异，规范化换行后全部一致。未修改线上文件、配置或服务。

原始发布清单保存在 [发布清单](releases/live-20261012.manifest.json)，无凭据及生产对话。
首页和 `/healthz` 本次均返回 200，后者为 `{"status":"ready"}`。
这些检查证明发布文件对应关系和基础可达性，不证明每项业务、模型回答或实地导航均通过。
Pages 入口的边缘代理配置本次未导出，不属于这份后端发布清单。

### 运行配置

读取正在运行进程的环境，仅提取以下非敏感配置。没有保存完整环境或密钥。
“代码默认”表示该变量未在进程环境设置，由锁定提交中的 `config.py` 提供默认值。

| 变量 | 生效值 | 来源 |
| --- | --- | --- |
| `CAMPUSPILOT_RUNTIME_MODE` | `phase2` | 进程环境 |
| `CAMPUSPILOT_AGENT_LOOP` | `on` | 进程环境 |
| `CAMPUSPILOT_RETRIEVAL_MODE` | `hybrid` | 进程环境 |
| `CAMPUSPILOT_GROUNDING` | `flag` | 代码默认 |
| `CAMPUSPILOT_JEV` | `off` | 代码默认 |
| `CAMPUSPILOT_KNOWLEDGE_BUNDLE` | `approved-20261011b` | 进程环境 |
| `CAMPUSPILOT_ASSET_VERSION` | `auto` | 进程环境 |
| `CAMPUSPILOT_MODEL` | `deepseek-flash` | 进程环境 |
| `CAMPUSPILOT_EMBEDDING_MODEL` | `@cf/baai/bge-m3` | 代码默认；向量清单也记录此模型 |
| `PUBLIC_ORIGIN` | `https://campuspilot.38-244-61-184.sslip.io` | 后端进程环境，区别于用户访问入口 |

提示词包含在锁定代码及其文件哈希中。模型服务的具体内部版本不由此提交锁定；相同模型名称
不保证将来的回答完全一致。Jev 的 on/shadow 实现与相关实验保留，但当前线上是 off。

### 知识快照

以下为线上文件字节 SHA-256，亦包含在发布清单中：

| 文件（`data/cdut/rag/approved-20261011b/`） | SHA-256 |
| --- | --- |
| `manifest.json` | `39d4f393a61b2fc9ba962f4e5d1a727b59922e7e1846fe8b2b1dd75ab1ec8240` |
| `snapshot.json` | `b774816081d3acb82ca45661568df37bddd0c56cff3fb7bda5ce22501d5ec8cc` |
| `vectors.sqlite` | `05ac3627ebb4d3d93b13d090071f2694f0e2004e9fec6c8245563d2579acebca` |

该包为 158 个来源、287 个片段，向量清单记录 287 行、1024 维。
快照固定不代表资料永久有效，也不改变原有审核状态或限制。

### 本地整理与未上线工作

- 主工作目录：`D:/Projects/CampusPilot`；整理分支 `chore/live-baseline-20261012` 基于上述线上提交，
  经 PR 合入后回到 `main`。长期分支只保留 `main`，上线版本通过 `v0.1.0` 等标签记录。
- 已部署的 `backend/`、`data/`、依赖文件保持原样；本轮更新文档、保存清单并增加离线核对脚本。
- 地图修改保留于 `D:/Projects/CampusPilot-map-acceptance`，分支 `fix/map-coordinate-acceptance-20261012`。
  其中本地坐标转换和错误重试改动仍未提交、未上线，不混入线上基线。
- 用户反馈手机端地图使用正常，截图问题发生在电脑端。这是用户使用反馈，不替代全机型测试；
  电脑端故障原因尚未确定。下一次排查先复现电脑浏览器定位、转换请求与错误恢复，再决定修复范围。
- PR #5 已将完整线上代码纳入 `main`。PR #25 的最终评分报告以 `main` 为目标归档，其测试提交是
  `2fafe091`，不得描述为本次上线提交的完整验收报告。历史分支收拢见 [仓库维护](REPOSITORY_WORKFLOW.zh-CN.md)。
- 历史目录、旧 CLI、classic 页面、Dify 材料和旧部署脚本保留，避免破坏导入路径、测试与回滚参考。

### 核对与后续更新

从仓库根目录运行 `python scripts/check_live_baseline.py`。脚本只读本地，不连服务器，不请求模型，
对照保存的发布清单核对发布范围文件；文本仅允许 CRLF/LF 差异。缺失、内容差异或新增发布文件
均返回非零。它不是测试套件，也不能据此声称服务器仍运行同一版本。

本轮整理检查：本地 120 项清单比对通过；核对脚本的原样、CRLF、内容修改、文件缺失、
新增发布文件及清单版本损坏 6 类场景通过；脚本 Ruff 与 mypy 通过；修改文档的本地链接
和 Git 空白检查通过。运行代码未修改，未执行付费模型评测。

GitHub 整理时追加验证：Node 37 项通过，Ruff 通过，mypy strict 100 个文件通过。
将 `31ed5bb` 用 `git archive` 独立导出，并明确 PYTHONPATH 后在 Windows / Python 3.14.7
执行全量 pytest：456 通过、21 失败。16 项涉及固定评测集 `cases.jsonl` 哈希与清单不一致，
2 项涉及历史 `approved-20261011` 知识包的重建/校验，3 项涉及 Windows 上 POSIX 符号链接
切换测试。线上当前使用 `approved-20261011b`，其发布文件哈希仍全部匹配。
这些是既有提交的未解决问题，不把本次主线整理或版本标签称为全部测试通过。

下次实际发布后，重新保存清单、核对运行配置与前端资源版本，再更新本记录。不得只改版本号
或用分支名称替代完整提交 SHA；部署与独立 QA、最终合并是不同事项。

仍待完成：电脑端地图复现、最新整合版本的独立 QA、老师查询与无依据回答的质量回归，以及
校园真实步行等尚未有证据覆盖的验收。此次整理不触发付费评测或重新部署。
