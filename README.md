# CampusPilot · 理小龙 CDUTdino

面向成都理工大学的校园事务助手：查询官方资料、办理步骤、老师和地点，结合高德地图提供步行参考路线与前台引导。当前范围为公开信息与只读辅助，不代办学校业务。

## 比赛版本与部署状态

正式入口为 **<https://cdutdino.pages.dev/>**。2026-10-21 22:53（America/Los_Angeles）只读核对服务器：
当前运行源码 `0f982edb2cc57d33bee9542c5c14b3031a775633`、运行包 `r-9431bf8d5c80`，
623 个发布文件逐项 SHA-256 一致；知识版本为 `kb-1d15bf97b31c0d90`，前端资源为 `ea0e123f8db8`。
完整身份、运行配置及证据边界见 **[线上基线](docs/LIVE_BASELINE.zh-CN.md)**。

| 状态 | 用途与身份 |
| --- | --- |
| 线上版 | 上述固定提交与运行包；保留松绿界面、读图、地图、学士帽恐龙、办理清单及 Jev/Search |
| 提交候选 | 从线上版继续收尾，唯一整合入口为 `D:/Projects/CampusPilot-integration`，复用 [PR #38](https://github.com/Debruyne-Luo/CampusPilot/pull/38)，待集中审阅 |
| 历史开发 | 其余六个工作区及旧报告原状保留；不从目录新旧或分支名推断线上状态 |

本轮收尾的工作区盘点、已有成果去重及交付要求见 **[提交版收尾](docs/SUBMISSION_CLOSEOUT.zh-CN.md)**。
GitHub `origin/main` 在本轮开始时为 `01d5318`，尚未包含 PR #38；本地 `main` 为 `715555e`，
不能把本地分支位置当作 GitHub 已合并。既有 Release 和附件保持不变，候选有独立版本身份。

最新已有回答验收为 **55/60**，Linux Python **1183 项**、Node **105 项**属于此前版本的记录，
不能冒充本轮修复结果。早期文档中的“未上线”“526”“57/60”仅描述各自测试阶段。
本轮候选复验为 **57/60**，原五项问题全部通过；Linux **1214 项**、Node **105 项**、Ruff 和
mypy（171 文件）通过。三项剩余缺口与原始观测见 [收尾核验](docs/qa/submission-closeout-20261022.md)。
这份候选尚未替换线上版本。

Harness² 保留源码及实验报告，`CAMPUSPILOT_HARNESS_PROFILE` 为空，学生页面没有实验室入口。
实验设计、报告与演示步骤见 [比赛设计](docs/SUBMISSION_DESIGN.zh-CN.md)、
[实验报告](docs/qa/harness-jev-20261020.md) 和 [演示脚本](docs/DEMO_SCRIPT.zh-CN.md)。
宣传片仅为本地实验材料，不进入提交包。真实手机、实际 GPS 路线与低端设备仍需独立验收。

## 代码入口

历史整合过程见 [整合记录](docs/INTEGRATION.zh-CN.md)；历史文件中的“未合入/未发布”仅描述当时状态。
知识更新继续遵守 [知识发布门槛](docs/KNOWLEDGE_REBUILD.zh-CN.md)，保留不可变版本与来源原件。

| 目录 / 文件 | 职责 |
| --- | --- |
| `backend/src/campuspilot/app/` | FastAPI 应用装配、聊天/数据接口、高德代理 |
| `backend/src/campuspilot/config.py` | 运行配置；代码默认值与线上显式配置不同 |
| `backend/src/campuspilot/agent/` | 理解、计划、只读工具执行和答案校验；保留旧 skeleton |
| `backend/src/campuspilot/tools/`、`directory/` | 校园事务、教师、地点与清单工具、结构化目录 |
| `backend/src/campuspilot/llm/`、`retrieval/` | 模型/嵌入适配与关键词、向量、混合检索 |
| `backend/src/campuspilot/web_assets/v2/` | 当前网页；地图 iframe 与引导脚本在 `web_assets/` 根目录 |
| `data/cdut/` | 结构化校园目录、知识资料与审核来源 |
| `data/cdut/rag/current.json`、`versions/` | 活动知识及回滚版本；旧 approved 包保留兼容 |
| `deploy/publish_release.py`、`deploy/_release.py` | 整包打包、文件校验、切换与回滚 |
| `scripts/` | 知识维护、提交包、评测及基线核对 |
| `tests/`、`evaluation/` | 自动测试、固定评测集和报告；结论仅适用于所记录的测试身份 |
| `integrations/dify/` | 历史 Dify 接入材料，不表示当前问答仍走 Dify |

旧 CLI、classic 网页和增量部署脚本保留作兼容与历史参考。新发布使用整包流程。

## 本地运行与检查

Python 固定为 3.14.7。先在仓库根目录执行（Windows 的 uv 如不在 PATH，可用 `%USERPROFILE%\.local\bin\uv.exe`）：

```powershell
uv sync --locked --extra api --extra vector
uv run --offline --locked --extra api python -m campuspilot.web
```

网页默认监听 <http://127.0.0.1:8766>。上述命令保留代码的 `legacy` 默认；复现线上 `phase2`
需按 [线上运行配置](docs/LIVE_BASELINE.zh-CN.md#运行配置) 显式设置开关，并在仓库外安全配置凭据。
[无密钥模板](deploy/vps/03-env.example) 中的占位符必须替换；图片、地图和付费工具不能仅凭开关验证成功。
没有模型或高德凭据时，仍可运行下面的离线合成演示：

```powershell
uv run --offline --locked python -m campuspilot demo
```

开发检查：

```powershell
uv run --offline --locked --extra api pytest -q
uv run --offline --locked --extra api mypy
uv run --offline --locked --extra api ruff check
node --test tests/*.test.js tests/*.test.mjs
```

开发检查不能替代真实模型验收、手机浏览器或校园步行检查。Linux 发布检查是安装、符号链接切换与回滚的验收环境。
`scripts/check_live_baseline.py` 只读比较捕获的线上清单；候选有意改变运行文件时应如实报告差异，不能据此改写线上清单。

## 文档导航

- [线上版本与待验边界](docs/LIVE_BASELINE.zh-CN.md)：判断实际运行身份的首要入口。
- [提交版收尾](docs/SUBMISSION_CLOSEOUT.zh-CN.md)、[仓库维护](docs/REPOSITORY_WORKFLOW.zh-CN.md)：当前候选和历史工作区。
- [提交包运行与演示](docs/SUBMISSION_RUN.zh-CN.md)、[本轮核验](docs/qa/submission-closeout-20261022.md)：评委入口、安装说明和验证限制。
- [整包部署与回滚](docs/DEPLOY_RELEASE.zh-CN.md)：当前发布方式；其中带日期的旧状态属于历史记录。
- [Agent](docs/AGENT.zh-CN.md)、[检索](docs/RETRIEVAL.zh-CN.md)：核心实现和开关。
- [产品范围](docs/PRODUCT.md)、[架构与决策](docs/ARCHITECTURE.md)、[ADR](docs/adr/README.md)：范围、历史决定和待决事项。
- [工程规则](AGENTS.md)、[QA 与协作](OPS.md)：权限边界和验证要求。
- [历史迁移交付](docs/RUNTIME_MIGRATION.zh-CN.md)、[历史提交版记录](docs/SUBMISSION_STATUS.zh-CN.md)：保留当时证据，不作为当前部署清单。
