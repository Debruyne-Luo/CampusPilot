# CampusPilot · 理小龙 CDUTdino

面向成都理工大学的校园事务助手：查询官方资料、办理步骤、老师和地点，结合高德地图提供步行参考路线与前台引导。当前范围为公开信息与只读辅助，不代办学校业务。

## 比赛版本与部署状态

2026-10-21发布整合已完成本地实现与自动检查，目标迁移至Ubuntu新机并保留原网址。
当前工作结果与未通过的问答样本见 **[发布交接](docs/qa/release-20261021.md)**：
Linux 1180项、Node 101项通过，真实问答57/60，原六个问题全部通过。宣传片仅本地保留。
现有正式入口本次核对返回526，下表保留上一次部署记录，不能作为当前健康状态证明。

2026-10-20 用户批准三个展示方向：校园任务联动、Harness² 策略优化、Jev 工具路由与证据判断。
本地增量的设计、启动方式、实验范围和验收结果以 **[比赛设计文档](docs/SUBMISSION_DESIGN.zh-CN.md)** 为入口。
优化器在独立 Linux/Python 3.12 环境运行，普通问答保持 Python 3.14.7；实验室为只读页面 `/lab`。
Search／Fetch 由独立工作负责，本增量复用既有联网证据契约。

真实执行与采用决定见 [实验报告](docs/qa/harness-jev-20261020.md)，操作顺序见
[演示脚本](docs/DEMO_SCRIPT.zh-CN.md)。候选暂不全局启用；源码、数据与结果身份见
[本轮版本清单](evaluation/agent-lab-20261020/submission-version.json)。

以下为已有部署记录，不能把本地实验室和新路由称为已上线。

| 项目 | 当前值 |
| --- | --- |
| 网站 | <https://cdutdino.pages.dev/> |
| 记录的部署代码 | `eba182cce42aa8ff506a04aa3738cdf5ced818d6`（2026-10-15） |
| 记录的发布包 | `r-62d8e21843ee`；完整运行身份仍需发布前重新核对 |
| 知识库 | `approved-20261011b` / `kb-f08fa4fd8b583700` |
| 运行模式 | `phase2`，Agent loop `on`，检索 `hybrid` |
| 生成 / 嵌入模型 | `deepseek-flash` / `@cf/baai/bge-m3` |
| 证据判断 | grounding `flag`（只标记），Jev `off` |

完整记录、配置来源、文件清单和待验边界见 **[线上基线](docs/LIVE_BASELINE.zh-CN.md)**。
这是一份部署事实记录，不等同于独立 QA 或产品验收通过。

GitHub `main` 是唯一长期主线；办理清单、桌面整合、GPS 修正和读图实现已合入。
标签 `v0.1.0` 固定此前版本，不代表当前线上提交；发布事实见上述清单。
临时 `feat/`、`fix/` 等分支在 PR 合入后清理，流程及历史分支记录见
[仓库维护](docs/REPOSITORY_WORKFLOW.zh-CN.md)。真实手机和校园实走仍须独立验收。

## 代码入口

本轮工作区为 `CampusPilot-integration`，隔离分支为 `feat/harness-jev-submission-20261020`。
历史整合过程见 [整合记录](docs/INTEGRATION.zh-CN.md)；历史文件中的“未合入/未发布”仅描述当时状态。
新知识重采候选仍受 [知识发布门槛](docs/KNOWLEDGE_REBUILD.zh-CN.md)约束。

| 目录 / 文件 | 职责 |
| --- | --- |
| `backend/src/campuspilot/app/` | FastAPI 应用装配、聊天/数据接口、高德代理 |
| `backend/src/campuspilot/config.py` | 运行配置；代码默认值与线上显式配置不同 |
| `backend/src/campuspilot/agent/` | 理解、计划、只读工具执行和答案校验；保留旧 skeleton |
| `backend/src/campuspilot/tools/`、`directory/` | 校园事务、教师、地点与清单工具、结构化目录 |
| `backend/src/campuspilot/llm/`、`retrieval/` | 模型/嵌入适配与关键词、向量、混合检索 |
| `backend/src/campuspilot/web_assets/v2/` | 当前网页；地图 iframe 与引导脚本在 `web_assets/` 根目录 |
| `data/cdut/` | 结构化校园目录、知识资料与审核来源 |
| `data/cdut/rag/current.json`、`versions/` | 整合版活动知识及回滚版本；旧approved包保留兼容 |
| `deploy/publish_release.py`、`deploy/_release.py` | 整包打包、文件校验、切换与回滚 |
| `scripts/` | 知识维护、导入导出、评测及基线核对 |
| `tests/`、`evaluation/` | 自动测试、评测集和报告；报告结论仅适用于其测试版本 |
| `integrations/dify/` | 历史 Dify 接入材料；不代表当前在线问答仍走 Dify |

旧 CLI、classic 网页和增量部署脚本保留作兼容与历史参考，不因整理而删除。新发布使用整包流程。

## 本地运行与检查

Python 固定为 3.14.7。先在仓库根目录执行（Windows 的 uv 如不在 PATH，可用 `%USERPROFILE%\.local\bin\uv.exe`）：

```powershell
uv sync --locked --extra api --extra vector
uv run --offline --locked python scripts/check_live_baseline.py
uv run --offline --locked --extra api python -m campuspilot.web
```

网页默认监听 <http://127.0.0.1:8766>。最后一条命令保留代码的 `legacy` 默认；它不等价于线上 `phase2`。
未配置模型和高德凭据时，不能验证真实问答或高德地图。按线上基线复现时，使用
[基线中的运行配置](docs/LIVE_BASELINE.zh-CN.md#运行配置)，从仓库外安全配置凭据，不把生产环境文件复制进仓库。

```powershell
uv run --offline --locked --extra api pytest -q
uv run --offline --locked --extra api mypy
uv run --offline --locked --extra api ruff check
node --test tests/*.test.js tests/*.test.mjs
```

离线合成演示独立保留：`uv run --offline --locked python -m campuspilot demo`。
开发检查不能替代真实模型评测、手机/电脑浏览器检查或校园实地步行验收。

## 文档导航

- [线上版本与待验边界](docs/LIVE_BASELINE.zh-CN.md)：判断现在运行什么的首要入口。
- [整包部署与回滚](docs/DEPLOY_RELEASE.zh-CN.md)：当前发布方式。
- [Agent](docs/AGENT.zh-CN.md)、[检索](docs/RETRIEVAL.zh-CN.md)：核心实现和开关。
- [产品范围](docs/PRODUCT.md)、[架构与决策](docs/ARCHITECTURE.md)、[ADR](docs/adr/README.md)：范围、历史决策和待决事项。
- [工程规则](AGENTS.md)、[QA 与协作](OPS.md)：权限边界和独立验证要求。
- [历史迁移交付](docs/RUNTIME_MIGRATION.zh-CN.md)、[历史提交版记录](docs/SUBMISSION_STATUS.zh-CN.md)：保留当时证据，不作为当前部署清单。
