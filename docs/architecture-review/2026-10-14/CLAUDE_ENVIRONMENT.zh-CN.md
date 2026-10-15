# Claude Code 本机核验与审计入口

核验日期：2026-10-14（Asia/Shanghai）。仅执行安装/帮助/认证状态与终端 `doctor` 诊断；未发起模型请求，未安装、升级或修改配置。此记录没有密钥、认证令牌或私有端点地址。

## 实测环境

| 项目 | 结果 |
| --- | --- |
| Claude Code | `2.1.299`，npm-global；实际程序 `E:\Claude Code\Nodejs\node_global\node_modules\@anthropic-ai\claude-code\bin\claude.exe` |
| Node / npm | `v24.21.0` / `11.19.0` |
| Git / Git Bash | `2.52.0.windows.1` / `5.2.37`；Git Bash 可执行文件为 `E:\Git\Git\bin\bash.exe` |
| PowerShell / OS | `7.6.5` / Windows 11 x64 |
| Python / uv | 项目 `.venv` 为 Python `3.14.7`；uv `0.12.19` 位于 `%USERPROFILE%\.local\bin\uv.exe`，当前不在 PATH |
| doctor | 退出 0，`No installation issues found`，bundled search `OK` |
| auth status | 退出 0，`loggedIn=true`、`authMethod=oauth_token`、`apiProvider=firstParty`；只证明 CLI 识别到凭据配置 |

已执行 `claude --help`、`claude --version`、`claude auth --help`、`claude auth status --help`、`claude auth status --json`、`claude doctor --help`、`claude doctor`。终端 doctor 是只读诊断，不等同于可应用修复的交互式 `/doctor`。[官方安装诊断](https://code.claude.com/docs/en/setup#verify-your-installation)

## 模型与配置事实

- 当前用户设置和进程将模型映射为 `anthropic/claude-opus-5.5[1m]`，显示名 `Opus 5.5`，默认 effort 为 `medium`。
- `ANTHROPIC_BASE_URL` 是 HTTPS 自定义网关；`ANTHROPIC_AUTH_TOKEN` 已设置，`ANTHROPIC_API_KEY` 为空。doctor 明确当前不是活跃的 claude.ai 订阅认证。
- 官方 Anthropic ID 为 `claude-opus-5-5`，Claude Code 至少需要 `2.1.280`；本机版本满足。网关命名由网关映射决定，不应把官方 ID 直接替换进用户现有设置。[官方模型配置](https://code.claude.com/docs/en/model-config)
- 未验证：网关认证是否实际成功、路由是否真实 Opus 5.5、是否提供 1M 上下文、账号额度、费用及模型质量。配置字符串与 `auth status` 均不能证明这些事项；正式会话开始时核对 `/status`，实际后端路由还需网关侧证据。
- 用户全局存在一个 MCP server 和 Bash/Web 权限。目标仓库、祖先目录未发现 `.claude/`、`CLAUDE.md` 或 `.mcp.json`；本机未发现系统 managed settings/MCP 文件。本次没有连接该 MCP。

## 待用户启动的只读审计会话

先运行 [输入核对](README.zh-CN.md#开始前核对输入)，然后手动执行下面的交互式命令。它保留现有网关认证，限定内建工具为 `Read,Glob,Grep`，通过 safe mode 停用用户自定义扩展；提示词要求显式读取根 AGENTS 和审查资料。不会自动读取 Git 状态或执行测试，因此应先完成外部输入核对。

```powershell
Set-Location -LiteralPath 'D:\Projects\CampusPilot-integration'
claude --safe-mode `
  --tools 'Read,Glob,Grep' `
  --permission-mode plan `
  --strict-mcp-config `
  --mcp-config '.\docs\architecture-review\2026-10-14\empty-mcp.json' `
  --disallowedTools 'mcp__*' `
  --model 'anthropic/claude-opus-5.5[1m]' `
  --effort high `
  --append-system-prompt-file '.\docs\architecture-review\2026-10-14\PRINCIPAL_ARCHITECT_PROMPT.zh-CN.md'
```

进入会话后先用 `/status` 核对模型配置，再发送：

```text
开始 Principal Architect 架构审计。审查 D:\Projects\CampusPilot-integration 的当前工作区，
按已加载的审计提示词先读取审查包及权威工程规则，覆盖未提交增量。
先列出审查对象和证据限制，再沿关键调用链核查，最后在会话输出完整中文 Markdown 审计报告。
本轮保持项目只读，建议均为 PROPOSED。
```

上述参数由本机 help 与官方文档核实；组合会话尚未启动，不宣称已完成网关连通或工具隔离验收。`empty-mcp.json` 为有效的空服务器配置。safe mode 中管理员 policy 仍可能适用；Read/Glob/Grep 的工具限制不构成操作系统文件沙箱。[官方 CLI 参数](https://code.claude.com/docs/en/cli-reference#cli-flags)、[MCP 配置](https://code.claude.com/docs/en/mcp#project-scope)

没有选用 `--bare`：其认证仅使用 API key 或显式 key helper，和当前 AUTH_TOKEN 配置不等价。[bare 认证规则](https://code.claude.com/docs/en/headless#start-faster-with-bare-mode)

本次审计不需要 Bash。将来若要在 Claude 中运行命令，可仅对该 PowerShell 会话设置 `$env:CLAUDE_CODE_GIT_BASH_PATH='E:\Git\Git\bin\bash.exe'`，再另行收窄命令权限；当前 PATH 的 `bash` 优先指向 Windows 系统入口，不能据此推定 Git Bash 已被选中。[Windows 安装说明](https://code.claude.com/docs/en/setup#windows)
