# CampusPilot — Grok 重构交接

日期：2026-10-11。仓库：[Debruyne-Luo/CampusPilot](https://github.com/Debruyne-Luo/CampusPilot)。
交接分支：`handoff/grok-refactor-20261011`。从此分支读取完整代码，默认 main 尚未包含这些改动。
这份交接提供代码与开发验证结果，不代表迁移已上线或通过独立 QA。

## 取得代码

```sh
git clone --branch handoff/grok-refactor-20261011 https://github.com/Debruyne-Luo/CampusPilot.git
cd CampusPilot
git rev-parse HEAD
```

记录实际读取和测试的 Commit SHA。重构请从该分支另建工作分支，提交可审查的 PR，
由用户保留最终 Review / Merge 权限。仓库工程约定见 [AGENTS](../AGENTS.md)。

## 代码与资料范围

| 路径 | 内容 |
| --- | --- |
| backend/src/campuspilot | 核心契约、合成演示、目录业务、HTTP 入口、会话、两阶段问答运行逻辑 |
| backend/src/campuspilot/web_assets | 原生网页、地图、周边查询与步行参考引导 |
| data/cdut | 公开校园结构化资料、来源记录、知识正文与审核元数据 |
| integrations/dify | 旧工作流与候选 DSL、提示词、知识生成文件；均不能冒充当前发布 v9 的锁定基线 |
| scripts、deploy | 基线捕获、知识维护、预算评测、候选打包、防漂移发布和失败回滚 |
| evaluation/runtime-migration | 固定 120 题、80 开发 / 40 保留、标签和独立 QA 模板 |
| tests、docs | 回归测试、产品 / 架构 / 接口 / 安全约定及实际交付限制 |

这次提交保留了此前未提交的网页、地图、目录、官方资料和后端迁移工作。
依赖由 pyproject.toml 和 uv.lock 声明。虚拟环境、缓存、备份 ZIP、运行日志、生产审计
留档与真实密钥不属于源码提交；本机的 `.test-runs/` 不会随 GitHub 克隆取得。
需要本地证据时，请由用户提供相应脱敏工件。

## 阅读顺序与重构边界

先读 [产品范围](PRODUCT.md)、[架构](ARCHITECTURE.md)、[接口契约](API_CONTRACT.md)、
[安全边界](SECURITY.md) 和 [ADR 0005](adr/0005-backend-runtime-and-knowledge-publication.md)，
再读 [迁移实现与维护命令](RUNTIME_MIGRATION.zh-CN.md)。旧文档中的历史阶段描述以较新的
已批准 ADR 和当前实现状态为准；不要把合成 Skeleton 当作生产问答入口。

重点入口是 web.py、chat_runtime.py、chat_model.py、rag.py 和 knowledge_release.py。
Jev 的适配与影子评测在 jev_shadow.py、migration_eval.py；发布门槛在 release_gate.py。
检查职责、依赖、重复代码和故障路径后，先给出具体改动清单，再按可审查范围实施重构。
重构应保持当前外部行为及以下已经批准的约束：

- 一个主 Agent、Python 模块化单体；不引入新数据库、向量服务或产品多 Agent 架构。
- 保留 `/api/chat` 答案、卡片、摘要、状态和请求 ID 契约，以及地图 / 移动端联动。
- 模型和 Skill 不能授予工具权限，模型输出不能伪造目录、坐标、校园规则或来源。
- 保留一小时会话、最近 8 轮上下文、身份 / 学年与事项隔离，以及限流和故障受限响应。
- 第一阶段保留冻结的 Dify 知识路径；第二阶段问答不创建 Dify 聊天客户端，也不在故障时回退 Dify。
- 知识审核绑定稳定片段 ID 和正文哈希；版本切换必须完整、原子，单次请求固定知识版本。
- OpenRouter Jev 只参与固定公开题的影子评测；结果不能改变线上路由、检索、权限或工具调用。
- 独立 QA、已发布基线及真实质量 / 性能验收未完成，不能通过修改状态或放宽测试来关闭门槛。

新增基础设施、模型供应商、向量实现或工具权限属于另外的架构决定，按现有决策流程处理。
保留集用于最终验收，不用于重构过程中的规则调优。不得删除原有能力的回归用例来使测试通过。

## 开发验证

本机 Python 3.14.7；锁文件与工具链见 [README](../README.md)。安装依赖后可离线执行：

```sh
uv sync --locked --extra api
uv run --offline --locked --extra api pytest -q
uv run --offline --locked --extra api mypy
uv run --offline --locked --extra api ruff check backend/src scripts deploy tests
node --check backend/src/campuspilot/web_assets/app.js
node --test tests/*.test.js
```

交接前结果：286 项 Python 测试通过；mypy strict 在项目默认范围检查 57 个文件通过；
Ruff 通过；网页语法与 9 项 Node 测试通过。Python 测试有一项 FastAPI / Starlette
测试客户端弃用提示。迁移运行候选的源码通过 Python 3.12 AST 检查，真实 Linux 3.12
执行仍待独立环境验证。完整结果及限制见 [开发验证记录](RUNTIME_MIGRATION_VALIDATION.zh-CN.md)。

重构后重新运行适用检查，报告实际 Commit SHA、命令、结果、契约变化和待验证项。
开发测试通过不等于独立 QA 或生产发布通过。

## 尚未完成的真实接入

默认运行模式仍为 legacy。未配置模型时，迁移路径的本地资料与 limited 响应可以测试，
无法据此证明生成答案质量或生产性能。新模型入口 / 模型 ID / 密钥、OpenRouter Jev
密钥与价格、Dify 管理 API 凭据由仓库外配置注入；空白模板与创建方式见迁移文档。

Dify 控制台已确认发布 v9，但其已发布 DSL 导出要求升级，发布基线为 NOT_LOCKED。
完整管理 API 文档 / 片段快照及审核映射还未取得；本地旧 v6 / 候选 DSL 不能替代。
新审核包已有 21 个来源、56 个检索片段；完整当前启用语料的保留核对仍待上述快照。
真实付费影子评测、完整 API 质量 / 时延评测、独立标签审核和 QA，以及第二阶段真实
Dify 网络阻断验收均待完成。每阶段外部推理仍按 5 美元 / 1,000 次的既定预算停止条件执行。

请把代码重构与这些验收缺口分别报告，保持发布门槛关闭直到取得所需证据。
