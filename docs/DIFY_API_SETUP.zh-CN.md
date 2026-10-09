# Dify 只读业务接口：本地开发版

2026-10-07 更新：提交版采用已在 ADR 0004 确认的架构；新增地点、教师及统一 assist 接口。
本文以下为早期联调记录；新增接口见 [接口契约](API_CONTRACT.md#confirmed-submission-increment-2026-10-07)，
云端配置见 [部署说明](SUBMISSION_DEPLOY.zh-CN.md)。

2026-10-03：依据用户“减少重复检索测试、开始下一步工作”的授权，增加可选 FastAPI HTTP 适配试验。生产采用仍为 **PROPOSED**，部署方式 **OPEN**；没有新建 ADR、发布、提交或推送。

## 已实现的效果

HTTP 请求 → 凭据与参数校验 → ToolExecutor → Directory → 带来源证据的结构化结果。

查询已有三项事务和负责部门，返回完整字段、来源、未知值和待核验状态。每次请求有独立关联 ID 和执行记录。没有学校登录、实际办理、GIS 或模型调用。

**Dify Cloud 尚未调用此 API**。Cloud 无法访问本机 `127.0.0.1`；本轮没有开公网端口、建立隧道或部署服务器。可达的鉴权 HTTPS 入口落实后才能继续验证 Dify 联通。

后续新增的是反方向的 [Python → Dify 聊天接入与自定义网页](WEB_DIFY_SETUP.zh-CN.md)，不改变这里“Dify 尚未调用业务工具 API”的状态。

## 本机启动

在仓库根目录运行，Python 仍为 3.14.7。API 依赖可选，原 CLI 运行方式不变。

```powershell
uv sync --locked --extra api
# 凭据只放当前终端环境，不打印或提交。
$env:CAMPUSPILOT_API_TOKEN = (uv run --locked --extra api python -c "import secrets; print(secrets.token_urlsafe(32))")
uv run --locked --extra api python -m campuspilot.api
```

默认仅监听 `127.0.0.1:8765`，Ctrl+C 停止。密钥缺失、格式不合要求或数据损坏时启动失败，不回退到合成数据。启动时读取数据快照，更新 JSON 后需重启。

uv 不在 PATH 时，用 `& "$env:USERPROFILE\.local\bin\uv.exe"` 替代 `uv`。

## 接口

| 方法与路径 | 输入 | 输出 |
| --- | --- | --- |
| `GET /healthz` | 无；不要求凭据 | ready，仅表示配置和数据已加载 |
| `POST /v1/directory/services/search` | JSON：query，可选 academic_year | 候选事务及证据 |
| `GET /v1/directory/offices/{office_id}` | 事务结果里的准确部门 ID | 部门及证据，未知地点保留 null |

业务接口使用 `Authorization: Bearer <应用凭据>`，代表公开目录应用身份，不代表学生登录。额外 JSON 字段、查询参数均拒绝；客户端不能提供权限、数据路径、任意 URL 或执行身份。服务端生成关联标识，不信任客户端请求 ID。

请求例：`{"query":"缴费票据","academic_year":"2026-2027"}`。query 是事项名称/别名，不是整句自然语言；现有目录按子串匹配。Dify 意图提取和追问仍待连接。人群和渠道目前是结果中的适用条件，尚无对应确定性过滤接口。

响应保留 request_id、result、trace、固定提示；响应头带 X-Request-ID。领域字段保留 field_evidence、来源 URL、verification_status 和 null。

| HTTP 状态 | 处理 |
| --- | --- |
| 200 | 再读 result.status：success 或 empty；空结果不能由模型补造 |
| 401 | 缺失/错误凭据，返回安全 ApiError |
| 422 | 非法参数返回 ApiError；执行层校验失败返回非成功 result |
| 403 | 执行权限拒绝，返回非成功 result |
| 503 | 工具失败返回失败 result；其他边界异常返回 ApiError；不能当空结果 |

错误不回显输入、凭据或原始异常。执行记录按请求隔离，响应后不持久保存；这不是完整学生会话或审计系统。默认关闭访问日志。

## OpenAPI 与 Dify 接入

```powershell
uv run --locked --extra api python -m campuspilot.api --export-openapi docs/dify-directory.openapi.json
```

[OpenAPI](dify-directory.openapi.json) 由当前代码生成，仅含两个业务操作和 Bearer 安全声明。导出不监听端口、不需要真实密钥；未填虚构公开地址。Dify 导入兼容性尚未验证。

网络入口落实后的节点接法：

1. 提取事项名称，需要学年时先追问。
2. HTTP Request 节点 POST 到真实服务的事务查询路径，配置 JSON 与 Bearer 凭据。
3. HTTP 失败走失败回答；200 再区分 success/empty；多个候选先澄清。
4. 需要部门时使用返回的 office_id 查询；不要让模型生成 ID。
5. 根据实际结果回答；地点未知或 GIS 未接入时明确说明。

RAG 草稿保持可用。RAG 用于资料解释，API 用于结构化查询，后续交给同一个 Chatflow 编排。

## 验证与限制

```powershell
uv run --locked --extra api pytest -q
uv run --locked --extra api mypy
uv run --locked --extra api ruff check
uv run --locked --extra api ruff format --check
```

新增检查聚焦鉴权、非法输入、证据、空结果/故障及请求隔离，不重复模型检索评测。测试凭据明确为 synthetic。

本地版本尚无 TLS、限流、请求体大小限制、密钥轮换或持久日志；对外部署前需完善。请求隔离不代表整个 Agent 运行时线程安全。记录仍 needs_review，独立 QA 与人工事实复核未完成。

### 本轮运行记录（2026-10-03）

- Python 3.14.7；锁定 FastAPI 0.142.2、Uvicorn 0.54.0、Starlette 1.7.0。
- 新增 11 项 HTTP 边界检查；与原有 63 项一起通过，74 passed。mypy、Ruff 检查与格式检查通过。
- 真实回环 HTTP 请求验证：health ready，缺凭据 401，带凭据查询成功且记录仍 needs_review。验证后的临时进程已停止，临时随机凭据未写入文件。
- 默认 Windows Proactor 在本机出现 WinError 10014，启动入口现用标准库 SelectorEventLoop；未更换 Python 版本、关闭系统防护或添加事件循环依赖。此本地入口不支持子进程/管道类异步能力。Uvicorn 的事件循环机制参考[官方文档](https://uvicorn.dev/concepts/event-loop/)。
- Starlette 对测试客户端使用 httpx 发出弃用提示，当前测试可运行；不因该提示扩展本轮依赖迁移。
