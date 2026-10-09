# CampusPilot 网页与 Dify 对话接入

2026-10-07 更新：提交版已获批准并增加地点/教师/地图与结构化卡片。
本文保留 10 月 3 日联通记录；当前状态见 [提交版状态](SUBMISSION_STATUS.zh-CN.md)，
部署与新工作流配置见 [部署说明](SUBMISSION_DEPLOY.zh-CN.md)。

2026-10-03，依据用户确认分工后“开始接下来的工作”的指令，实施本地可选接入和网页。正式服务器部署、持久会话和 GIS 仍未实现。

**实际联通已完成（2026-10-03）**：用户明确授权后，发布 `CampusPilot-开发版` 工作流版本 #1，创建一枚应用 API 密钥并仅配置在本地运行进程。浏览器通过本地后端向 Dify 提问“2026-2027学年的学杂费电子票据在哪里下载？”，成功收到真实回答及 3 条检索片段，页面显示“AI 对话已连接”。仅做这一项真实联通验证，没有重复整套 RAG 测试。

密钥经用户授权的临时本机文件交给启动进程，文件已删除，剪贴板已恢复；未写入仓库、前端或普通日志。密钥本身仍在 Dify 有效，本地进程停止后要按下面的方法重新配置。Dify 托管 Web 应用也随已授权发布启用，不等于自定义 CampusPilot 已部署到服务器。

## 分工与实际路径

```text
浏览器 → Python /api/chat → Dify Chatflow → 知识检索、模型 → 浏览器
浏览器 → Python /api/catalog → 已校验的本地三事务记录 → 步骤、条件与官方来源
```

对话只由 Dify 编排。Python 新增的是协议适配、匿名会话隔离和页面服务，不新增模型提示词、自研推理循环或向量库。原 Fake Harness 留作合成测试，正式对话入口不调用它。

目录卡片是确定性资料展示，不是模型生成的结果。当前 Dify **仍未反向调用** Directory 工具 API，也没有 GIS。RAG 来自之前导入的派生语料，数据状态仍是 `needs_review`。

## 启动

在仓库根目录执行（Windows uv 不在 PATH 时使用完整路径）：

```powershell
& "$env:USERPROFILE\.local\bin\uv.exe" sync --locked --extra api
# 无凭据也可以查看网页和三项事务；AI 发送按钮明确禁用。
& "$env:USERPROFILE\.local\bin\uv.exe" run --locked --extra api python -m campuspilot.web
```

打开 <http://127.0.0.1:8766>。本地入口仅绑定回环地址，不向局域网或公网开放。

真实对话需先在 Dify 发布当前 Chatflow，再配置**该应用的 API 密钥**（不是模型供应商密钥、知识库管理密钥或账户凭据）。停止未配置的本地进程后运行：

```powershell
& "$env:USERPROFILE\.local\bin\uv.exe" run --locked --extra api python -m campuspilot.web --prompt-key
```

终端会隐藏输入，密钥只留在当前进程内存，不保存到文件或 shell 历史。也支持由部署环境注入 `DIFY_API_KEY`。缺少密钥时只展示未连接状态；不能据此宣称远端可用。

默认地址 `https://api.dify.ai/v1`。未来自托管时，由管理员设置 `DIFY_API_BASE_URL` 为对应 HTTPS API 地址，浏览器不能指定此地址。更改密钥或地址需要重启。未配置密钥的启动不访问 Dify。

## 页面与接口

| 接口 | 行为 |
| --- | --- |
| `GET /`、`/assets/*` | 自定义网页，纯 HTML/CSS/JS，无前端构建工具 |
| `POST /api/session` | 分配服务端随机匿名身份，通过 HttpOnly、SameSite=Strict Cookie 关联 |
| `POST /api/chat` | 仅接收 `{message}`，返回 answer、excerpts、notice、request_id |
| `POST /api/session/reset` | 开启新会话，重新分配身份；不删除 Dify 云端历史 |
| `GET /api/catalog` | 公开三事务及其字段证据和官方来源；不含学生信息 |

POST 要求同源 Origin 和 `X-CampusPilot-Request: 1`，不开放 CORS。浏览器不提交 Dify `user` 或 `conversation_id`，也不接收密钥、供应商调试信息或全部 metadata。

会话及 Dify 对话 ID 的关联保存在单进程内存；有效期一小时，上限 256 个会话，每会话最多 40 次请求，同一会话仅允许一个请求在途。刷新保留服务端对话关联，但浏览器不恢复旧消息；重启丢失本地关联。没有跨设备历史和真实用户账户。

网页将模型文本作为文本渲染，不执行 HTML，也不加载模型生成的图片或脚本。官方来源链接仅由经校验的目录数据生成。检索片段单独标为“资料待核验”，不把检索命中等同于事实核验。

## 错误与验证范围

当前使用 Dify `blocking` 模式，完成后一次返回；不是流式展示。连接超时 10 秒，读取超时 90 秒，总时限 95 秒；浏览器等待上限 105 秒。远端超时后可能仍在执行，禁止自动重试并要求新对话，避免误报成功或重复消耗。未配置、认证失败、限流、超时、非法响应均呈现真实错误，不使用假回答兜底。

本轮开发检查：86 项通过（新增 12 项），mypy、Ruff 通过。新增检查使用明确 synthetic 上游，覆盖会话关联与隔离、重置、并发拒绝、鉴权错误、重定向拒绝、超时与畸形响应、请求大小、跨站请求、客户端身份覆盖以及密钥不出现在前端响应。它们不代表真实 Dify 已连接；实际联通另行记录。

## 后续

1. 已完成发布、凭据配置和一次真实问答；继续完善回答排版与来源展示，不重复检索回归。
2. 落实服务地址后，将 Dify 的 HTTP 节点接入业务查询 API；当前网页目录卡片无需这条反向连接。
3. 补齐有依据的地点数据，再开发地图与 GIS 工具。
4. 部署前补齐 HTTPS、真实访问控制、全局调用预算与限流、持久会话、密钥管理、日志与备份。本地的匿名 Cookie 和每会话上限不等于公网访问控制或防刷措施。

开发版没有学校登录、个人资料查询、缴费、挂失提交或证明申请。问题会在真实连接后送往 Dify 与配置的模型服务；不要输入学号、密码、身份证号等私人信息。浏览器消息不写入 localStorage；Dify 云端的日志和保留策略需在上线前单独配置。

## 依据

- [Dify API 入门](https://docs.dify.ai/en/api-reference/guides/get-started)
- [Chatflow API](https://docs.dify.ai/en/api-reference/guides/chatflow)
- [发送聊天消息](https://docs.dify.ai/en/api-reference/chat-messages/send-chat-message)

官方接口核查日期：2026-10-03。密钥不进入前端；Dify End User 标识仅用于上游数据隔离，不作为学生身份认证。
