# Principal Architect 审查准备包

本次目标是让 Claude Code / Opus 5.5 能对**最新本地进度**进行有证据的架构审计。准备日期：2026-10-14（Asia/Shanghai）。本包不构成架构审计结论、产品验收或发布许可。

## 审查哪一份项目

使用 `D:\Projects\CampusPilot-integration`，分支 `feat/desktop-backend-integration`。

| 截面 | 身份与用途 |
| --- | --- |
| 最新完整审查对象 | `a38842beea6afd8d4ca66a15e39ef0ea0d596531` **加当前未提交工作区**；按 [REVIEW_INPUTS.json](REVIEW_INPUTS.json) 的 961 项字节指纹识别 |
| 已提交融合实现 | `893abcb` 融合后端 `3c0c395` 和桌面 `f3dc8ed`；后续到 `a38842b` 是交接文档 |
| 当前未提交增量 | 官方资料导入/发现、不可变知识发布与恢复、回答中的官方办事链接、对应测试和本地知识版本 `kb-229ee34eba99ef34` |
| 主目录 | `D:\Projects\CampusPilot` 仍在 `5fd207c`，另有未跟踪设计资料，不是最新融合工作区 |
| 线上存档 | [LIVE_BASELINE](../../LIVE_BASELINE.zh-CN.md) 记录 `258ff205` / `r-994da5858c65`；本次未连接生产复核 |

清单采集时为 2026-10-14 20:01:59 +08:00：15 个已跟踪文件修改、329 个未跟踪文件，共 46 条折叠状态记录。所有原有文件均保留。审查包独立新增于本目录，没有改核心代码、依赖、知识、测试预期、根工程规则或 Claude 全局设置；没有提交、推送、合并、部署，也未启动 Claude 模型审计。

## 给审查者的入口

1. 读 [SYSTEM_MAP](SYSTEM_MAP.zh-CN.md)：代码入口、模块边界、五条关键调用链、数据与信任边界、测试地图和文档漂移。
2. 读 [VERIFICATION](VERIFICATION.zh-CN.md)：这次实际执行的检查、失败与限制；历史 QA 不能代替当前工作区证据。
3. 读 [SKILL_REFERENCES](SKILL_REFERENCES.zh-CN.md)：固定版本的 Matt Pocock 方法及本次采用范围。
4. 读 [CLAUDE_ENVIRONMENT](CLAUDE_ENVIRONMENT.zh-CN.md)：CLI/网关检查结果及待人工启动的只读命令。
5. 将 [PRINCIPAL_ARCHITECT_PROMPT](PRINCIPAL_ARCHITECT_PROMPT.zh-CN.md) 用作正式审计任务。审计覆盖整个当前系统，同时把未提交增量单独标记。

## 开始前核对输入

在目标目录执行，只读、无网络、不安装依赖：

```powershell
Set-Location -LiteralPath 'D:\Projects\CampusPilot-integration'
& '.\.venv\Scripts\python.exe' -X utf8 -B '.\docs\architecture-review\2026-10-14\verify_inputs.py'
```

退出 0 且 `matches_captured_inputs=true` 才能沿用本包的版本绑定。新增、删除、字节变化、HEAD 或分支变化返回 1；清单/运行错误返回 2。已有工作继续推进时，应生成新的有日期截面并重新核对验证范围，不能把旧清单直接覆盖成“已验证”。本包不是代码备份；未提交内容不能仅靠 HEAD 从 GitHub 恢复。

清单覆盖 Git 已跟踪与未忽略的未跟踪文件，排除本审查包目录以避免自引用；忽略的 `output/`、虚拟环境、缓存和私密配置不属于输入。审查源码从地图进入，原始 HTML/PDF/图片只按具体证据需要抽查，不要把整个原始资料目录灌入模型上下文。

## 准备完成标准

- 项目与版本身份明确，未提交增量没有遗漏，原有内容指纹保持一致。
- 审查者能从用户请求追到工具、证据、模型、前端和发布，并找到相应失败测试。
- 当前实测、历史报告、静态推断和待验事项各自标记。
- Claude CLI 安装与配置已核验；网关真实模型和账号访问保持待会话确认。
- 审计产物要求包含证据、影响、反例、最小建议、迁移/回退和验证方法；建议保持 **PROPOSED**。
