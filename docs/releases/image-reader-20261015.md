# 发布记录：图片理解上线（独立读图模型）

## 版本身份

| 项目 | 结果 |
| --- | --- |
| 用户入口 | https://cdutdino.pages.dev/ |
| 源码提交 | `eba182c`（main，PR #36） |
| 发布目录 | `/opt/campuspilot/releases/r-62d8e21843ee` |
| 发布文件数 | 255 |
| 知识包 | `approved-20261011b`（未改） |
| 回滚目标 | `r-869cfdc79a57` |

## 为什么需要独立读图模型

原实现只有一个模型同时负责文本答题与图片理解。实测两个可用 DeepSeek 模型
（`deepseek-flash`、`deepseek-v4-pro`）对图片输入返回空内容、纯文本正常，即无法读图；
而直接换成能读图的 Gemini 会让**全部文字回答**降级为 `limited`（其 JSON 不满足
`GroundedAnswer{answer, source_ids, status}` 契约，观测到 `degraded_reason=model_format`）。

因此新增 `CAMPUSPILOT_READER*`：图片相关调用走独立读图模型，文本答题仍用原模型。
未配置 reader 时回退主模型，行为与之前完全一致。

## 服务器配置（非发布内容）

`/etc/campuspilot/campuspilot.env`（改动前备份 `campuspilot.env.bak-reader`）：

```dotenv
CAMPUSPILOT_MODEL=deepseek-flash           # 未改，文本答题继续用它
CAMPUSPILOT_READER=gemini-3.5-flash-lite
CAMPUSPILOT_READER_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
CAMPUSPILOT_READER_API_KEY=…               # 仓库外，不记录
CAMPUSPILOT_READER_TIMEOUT=40
CAMPUSPILOT_READER_MAX_TOKENS=2000
CAMPUSPILOT_IMAGES=on
```

先前发布前必须先在 venv 补 `pillow`（本轮已装：`pillow 12.3.0`），且网关需保留
`/api/attachments` 的 10MiB 例外，否则上传会得到 413。

## 发布后验证（外部访问，合成课表图片）

- 首页、`/healthz` 200；`/api/session` 返回 `images_enabled: true`、`model_configured: true`。
- 文字问答「校园卡丢了怎么补办？」：`success`、7 条引用，与换模型前一致（无回退）。
- 图片问答：上传 38607 字节课表 → 7 秒返回 `status=success`、`mode=agent_image`，
  「高等数学 A、周二 08:00-09:40、第四教学楼 B 区 301」，与图片内容逐项一致。

## 模型可用性实测（2026-10-15）

| 模型 | 读图 |
| --- | --- |
| `gemini-3.5-flash-lite` | 可用，答案与图片完全一致（当前选用） |
| `gemini-3.6-flash` | 可用，但小 `max_tokens` 下会被思考 token 截断 |
| `gemini-3.8-flash` | 503 容量不足 |
| `gemini-4-argon` | 429 该 Key 无配额 |
| `deepseek-flash` / `deepseek-v4-pro` | 返回空内容，不能读图 |

图片内容始终标注「用户上传、未经学校核验」。
