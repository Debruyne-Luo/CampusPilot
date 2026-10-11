# CampusPilot Agent 循环（P3）

开关：`CAMPUSPILOT_AGENT_LOOP=on`（仅 `phase2` 生效；默认 off，走原规则运行时）。

流程：`agent/understand.py` → `agent/plan.py` → `agent/executor.py` → `agent/verify.py`

1. **理解**：LLM 输出 JSON（intent ∈ 办事/找人/找地点/路线/政策问答/闲聊；slots：identity、academic_year、service、destination；missing、clarify_question）。正则身份/学年为准；文本中没有的学年丢弃；模型失败回退规则理解。
2. **澄清**：missing 非空（且会话上下文无法补齐）时直接返回 `needs_clarification`，不调用工具。
3. **计划**：代码确定的 1-4 步工具计划（展示给用户，不由模型生成）。
4. **执行**：先跑计划步骤；再让模型通过 function calling 追加只读工具调用（ToolRegistry 白名单 + pydantic 参数校验），最多 3 轮，第 4 轮强制无工具作答。
5. **校验**：引用 ID 必须来自本轮工具结果，success 必须有引用；禁止 URL/坐标；3 位以上数字须出现在证据中；“余额大于20”等关键前提必须保留（与规则路径共用 `agent/verify.py`）。
6. **降级**：模型不可用/超轮/校验失败 → 资料摘要（`result_status=limited`，`degraded_reason`）。

响应在原字段基础上新增可选：`plan`、`checklist`、`citations`、`map_actions`（`plan_route` 只给目的地 place_id，起点由前端浏览器定位，个人坐标不进后端）、`understanding`。
敏感信息（密码、账号、个人位置等）在调用任何模型前拦截。SSE 流式留到 P4。
