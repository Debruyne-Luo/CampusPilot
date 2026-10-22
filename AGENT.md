# Agent 定义：理小龙 CDUTdino

这是可在本地运行的 Python Agent 应用文件包。启动入口是 `run_agent.py`，运行时角色提示词位于 `backend/src/campuspilot/agent/executor.py` 的 `AGENT_SYSTEM`；本文件用于说明实际实现，不会被当成一份额外系统提示词自动加载。

## 目标与职责

帮助成都理工大学用户从公共资料中找到办事依据与下一步。输出简明答复、可点击来源、办理清单、教师或地点卡片；支持读图和按需联网补证。用户本人完成登录、申请、缴费与预约，Agent 不代办、不宣称业务已经完成。

## 输入与输出

- 输入：自然语言问题、当前会话最近消息，以及用户主动上传的图片。只有会改变结论的身份、届次或事项条件缺失时才澄清。
- 输出：经过解析与校验的答复、来源标识、状态、卡片及地图动作。HTTP/SSE 消费接口保持现有字段，浏览器只展示结果及执行状态，不展示内部推理。
- 失败：模型未配置、证据不足、错误 JSON、超时、超预算或工具拒绝均有明确状态；程序可以保留有来源的目录指引，不把它伪装成模型成功。

## 实际执行链

`理解与条件核对 → 程序生成有限计划 → 授权工具执行 → 汇总本轮证据 → 模型组织答复 → 引用与关键事实校验 → 展示结果`

主执行器只有一个 `AgentRunner`。程序计划最多 4 步；模型补充工具调用最多 3 轮。图片 reader、Jev 判断插件和检索器都是主 Agent 使用的能力，不各自承担一个自治 Agent。清单与地图动作由程序按业务记录生成。

## 工具与权限

| 能力 | 实际工具/模块 | 约束 |
| --- | --- | --- |
| 办事与清单 | `search_service`、`make_checklist`、`find_office` | 只读公开事项；清单勾选仅是用户本地进度 |
| 校园知识 | `search_knowledge` | 当前固定知识发布版本；保留来源、适用人群和时效 |
| 教师与地点 | `search_teacher`、`find_teacher`、`search_place`、`list_places` | 使用已有记录或显式启用的地图查询；不创造坐标和联系方式 |
| 图片阅读 | `attachments.py` 与独立 reader 配置 | 用户上传图片是输入资料，不能成为官方政策依据 |
| 外部补证 | Jev 路由/证据判断 + `search_web` 的 Search/Fetch | 显式开关、费用限额、证据可追溯；默认关闭 |

参数经 `ToolRegistry` 的 Pydantic 模型校验；调用先经过 `ExecutionBoundary` 的能力声明和只读权限。模型文字、外部网页与图片都不能新增权限。

## 证据规则

1. 校园事实依本轮可用来源作答，不用上一轮模型回答充当证据。
2. 目录、检索摘要和“仅有链接”的来源，只支持其已有信息范围；不能外推出正文未核对的办理步骤。
3. 保留资料的日期、届次、必要材料和限制。历史通知不自动变成现行规则。
4. 引用只能取本轮提供的标识；不编造电话、金额、期限、坐标、网址和成功状态。
5. 官方原文与运行时输出共同决定可信范围；校验是有限的程序检查，不能保证所有自然语言事实都正确。

## 核查代码的位置

| 评审问题 | 代码入口 |
| --- | --- |
| 谁负责主循环？ | `agent/executor.py::AgentRunner` |
| 如何理解、规划和限制循环？ | `agent/understand.py`、`agent/plan.py`、`MAX_TOOL_ROUNDS` |
| 模型能调用什么？ | `tools/__init__.py::agent_registry`、`agent/execution.py::ExecutionBoundary` |
| 证据从何而来？ | `rag.py::SnapshotStore`、`tools/knowledge.py`、`web_evidence.py` |
| 如何阻止无依据输出？ | `agent/structured_answers.py`、`agent/verify.py`、`agent/responses.py` |

上表路径均相对 `backend/src/campuspilot/`。架构全图见 [架构说明](docs/architecture.md)。
