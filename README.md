# CampusPilot · 理小龙 CDUTdino

面向成都理工大学的校园事务助手：查询官方资料、办理步骤、老师和地点，结合高德地图提供步行参考路线与前台引导。当前范围为公开信息与只读辅助，不代办学校业务。

## 当前线上基线

**2026-10-12 已只读核对线上发布包、进程配置及仓库内容。后续整理以此版本为准。**

| 项目 | 当前值 |
| --- | --- |
| 网站 | <https://cdutdino.pages.dev/> |
| 已部署代码 | `31ed5bb0264d927c7918046b66b2947c013e8205` |
| 发布包 | `r-0f1805acf68e`，120 个文件哈希全部一致 |
| 前端资源版本 | `a44289c47acf` |
| 知识库 | `approved-20261011b` / `kb-f08fa4fd8b583700` |
| 运行模式 | `phase2`，Agent loop `on`，检索 `hybrid` |
| 生成 / 嵌入模型 | `deepseek-flash` / `@cf/baai/bge-m3` |
| 证据判断 | grounding `flag`（只标记），Jev `off` |

完整记录、配置来源、文件清单和待验边界见 **[线上基线](docs/LIVE_BASELINE.zh-CN.md)**。
这是一份部署事实记录，不等同于独立 QA 或产品验收通过。

GitHub `main` 是唯一长期主线，已通过 [PR #5](https://github.com/Debruyne-Luo/CampusPilot/pull/5)
纳入当前线上代码。标签 `v0.1.0` 固定实际部署提交；后续说明与评测报告可以领先于部署。
临时 `feat/`、`fix/` 等分支在 PR 合入后清理，流程及历史分支记录见
[仓库维护](docs/REPOSITORY_WORKFLOW.zh-CN.md)。本次整理不改变线上运行代码与数据。

用户于 2026-10-12 反馈手机地图使用正常，截图中的问题出现在电脑端。此前地图坐标修改仍单独保留在
`fix/map-coordinate-acceptance-20261012` 工作区，未提交、未上线，不属于此基线；电脑端问题待单独复现。

## 代码入口

| 目录 / 文件 | 职责 |
| --- | --- |
| `backend/src/campuspilot/app/` | FastAPI 应用装配、聊天/数据接口、高德代理 |
| `backend/src/campuspilot/config.py` | 运行配置；代码默认值与线上显式配置不同 |
| `backend/src/campuspilot/agent/` | 理解、计划、只读工具执行和答案校验；保留旧 skeleton |
| `backend/src/campuspilot/tools/`、`directory/` | 校园事务、教师、地点与清单工具、结构化目录 |
| `backend/src/campuspilot/llm/`、`retrieval/` | 模型/嵌入适配与关键词、向量、混合检索 |
| `backend/src/campuspilot/web_assets/v2/` | 当前网页；地图 iframe 与引导脚本在 `web_assets/` 根目录 |
| `data/cdut/` | 结构化校园目录、知识资料与审核来源 |
| `data/cdut/rag/approved-20261011b/` | 当前线上知识快照和向量索引 |
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
