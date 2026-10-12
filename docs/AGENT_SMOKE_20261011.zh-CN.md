# Agent 循环真实模型冒烟测试（2026-10-11）

- 分支：`refactor/04-p3-agent-loop`（PR #9）
- 模型：DeepSeek `deepseek-flash`（OpenAI 兼容，`https://api.deepseek.com`），会返回 `reasoning_content`
- 嵌入：Cloudflare `@cf/baai/bge-m3`；检索 hybrid
- 运行：本机进程内 `build_app(Settings.from_env())`，`CAMPUSPILOT_RUNTIME_MODE=phase2`、`CAMPUSPILOT_AGENT_LOOP=on`；密钥仅通过环境变量映射到 `CAMPUSPILOT_MODEL_API_KEY`，未写入仓库
- 每题新会话；耗时为 `/api/chat` 端到端（含嵌入与全部 LLM 调用）

## 结果（修复后的最终一轮）

| 问题 | 意图 | 状态 | 耗时 | LLM 调用 / 追加工具 | 校验 |
|---|---|---|---|---|---|
| 校园卡丢了怎么补办 | 办事 | success（含清单、3 个 show_place） | 7.4s | 2 / 0 | 通过，7 个引用 |
| 卡丢了咱整 | 政策问答 | success | 9.9s | 3 / 2 | 通过 |
| 怎么请假 | 办事 | needs_clarification（库中无请假事项） | 7.4s | 3 / 4 | 通过 |
| 王洪辉老师办公室在哪 | 找人 | success（网安楼204室，show_place） | 4.0s | 2 / 0 | 通过 |
| 从图书馆去食堂怎么走 | 路线 | needs_clarification（食堂多个；含 plan_route） | 5.6s | 2 / 0 | 通过 |
| 奖学金怎么申请 | 办事 | needs_clarification（库中无事项，给出资助中心） | 9.0s | 3 / 4 | 通过 |
| 证明怎么开 | 办事 | needs_clarification（问哪种证明） | 9.3s | 3 / 4 | 通过 |
| 在读证明怎么开 | 办事 | needs_clarification（问身份，未调工具） | 2.9s | 1 / 0 | — |
| 我的密码是123456… | — | 敏感拦截 | 0.2s | 0 | — |
| 你好呀，今天心情不错 | 闲聊 | success（本地回复） | 1.6s | 1 / 0 | — |
| 学生邮箱怎么激活 | 办事 | limited，degraded_reason=invalid_response | 10.4s | 3 / 2 | 拦截：答案写了 `https://` 链接（预期内降级） |

模型作答 8 题，7 题通过校验（87.5%），1 题因写 URL 被正确拦截并降级为资料摘要。
function calling、`response_format: json_object` 均可用；`reasoning_content` 被忽略不外露。
单次 LLM 调用 1.3–4.5s；端到端中位数约 7s，最长约 10s。

## 发现并修复的问题

1. **输出被截断**：`deepseek-flash` 是推理模型，推理 token 也计入 `max_tokens`，默认 700 时中文答案的 JSON 被截断（finish_reason=length）→ 解析失败。修复：最终作答使用 `ANSWER_MAX_TOKENS=1500`，`complete()` 支持 `max_tokens`、读取 `finish_reason`；截断时降级原因标为 `output_truncated`；提示词限制正文 ≤350 字。
2. **身份追问过度**：模型几乎每题都把 identity 列为缺失（10 题中 7 题澄清）。修复：只有匹配到的事项限定了身份（如研究生在读证明）才追问身份；只有办事意图且识别不到事项时才追问事项。
3. **引用 ID 被误判**：(a) 模型把清单条目键（`limit-3`、`step-4`）当引用 → 这些本地 UI 键被剔除，其余引用仍严格校验；(b) 服务步骤中 `place_ids` 列出的地点 ID 未被收录为可引用 ID → 所有 `*_ids` 列表都收录。
4. **老师问题被识别为找地点**：问题中出现目录内老师姓名时，意图修正为找人，计划用老师姓名调用 `search_teacher`（原来用“王洪辉老师办公室”作为查询词，结果为空）。新增 `DirectoryRepository.teachers()`。

以上问题都补了假 LLM 测试（`tests/test_agent_loop.py`，现 31 个）。

## 遗留 / 建议

- 口语“卡丢了咱整”匹配不到“校园卡补办”（靠模型追加工具调用才答出）；建议给事项补别名（“卡丢了”“丢卡”），这属于数据层面的修改。
- 请假、奖学金等事项未收录，属于知识库覆盖缺口，不是 agent 的问题。
- 模型偶尔写出 URL 或域名；带协议的 URL 会被拦截，裸域名（如 `mail.stu.cdut.edu.cn`）目前放行。是否也拦截裸域名，需要产品决定。
- 推荐配置：`CAMPUSPILOT_MODEL_BASE_URL=https://api.deepseek.com`、`CAMPUSPILOT_MODEL=deepseek-flash`、`CAMPUSPILOT_AGENT_LOOP=on`、`CAMPUSPILOT_RETRIEVAL_MODE=hybrid`；保持默认 45s 整轮超时与 3 轮工具上限（实测最多用到 1 轮追加工具）。可考虑把意图理解换成更快的非推理调用，以压低延迟（理解一步耗时 1.3–4.3s）。
