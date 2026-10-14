# 新前端与证据／图片后端整合交接

2026-10-14，**CONFIRMED**：用户批准将已完成的前后端增量保存、融合并上传 GitHub 草稿 PR。
本轮没有重新设计界面，没有合入 main 或部署。线上仍为 `258ff20` / `r-994da5858c65`。

## 代码身份与使用入口

- 共同基线：`5fd207c`，包含已上线的办理清单与交接说明；GitHub main 仍为 `0623600`。
- 后端源提交：`3c0c395`，分支 `feat/backend-evidence-media`。
- 桌面源提交：`f3dc8ed`，分支 `feat/desktop-field-notes`。
- 正式融合分支：`feat/desktop-backend-integration`，工作区 `D:/Projects/CampusPilot-integration`。

后续新功能从融合分支的已提交版本建立分支；原后端、桌面工作区保留独立来源，不继续双向复制改动。
前端布局、GSAP 动效、地图镜头／路线取消、GLB 恐龙与办理清单保持当前认可的设计。

## 融合内容

使用三方合并，将两个来源提交纳入同一历史；`index.html`、`main.mjs`、`map.mjs`、`sse.mjs`
四个冲突以经过指纹验证及浏览器测试的组合实现解决。新增附件选择／粘贴／预览／移除、
上传进度与重试、聊天附件引用、高德临时地点、来源及失败状态、新对话后端清理。
地图与聊天共用后端地点查询；供应商坐标只用于导航，个人实时位置不进入聊天或 Jev。

整合核对发现并补齐三处交付配置：

- 旧 VPS 依赖安装脚本加入 Pillow，与当前 API 依赖保持一致。
- 两份应用 systemd 单元加入 `StateDirectory=campuspilot`（0700），使
  `/var/lib/campuspilot/evidence-budget` 在 `ProtectSystem=strict` 下可写。
- 源码备份加入 mjs、GLB、字体、图标及可编辑 Blender 源；实际部署仍使用完整
  `deploy/_release.py` 发布包。建模脚本仅整理格式与变量名，未重新生成或改变 GLB 模型。

三个功能开关保持默认关闭，配置示例不含密钥。原始工作区的 QA 报告、overlay 和补丁是历史证据；
正式联调对象现在是融合分支。新版本检查见 [整合 QA](INTEGRATION_QA.zh-CN.md) 与
[前端联调](INTEGRATION_FRONTEND_QA.zh-CN.md)。

## GitHub 审核顺序

沿用办理清单 PR #27（`feat/handling-checklist` → `main`）。后端草稿 PR 以办理清单分支为 base，
统一前端草稿 PR 以后端分支为 base，避免评审重复看到前置改动。前置 PR 合入后，后续 PR 再调整 base。
两条来源分支和统一分支均保存到 origin；没有强制推送、移动 main 或修改线上发布状态。

这种堆叠只表达审核依赖，不代表可以跳过验收。最终 Review / Merge 由 Tech Lead 决定，发布单独执行。
仓库目前没有 GitHub Actions 工作流，不能将本地检查称为 GitHub CI 通过。

## 已知验收边界

旧后端检查是 Windows CRLF 工作区的 600 passed / 21 failed，对照旧基线为 456 passed / 同21 failed；
[失败 ID 记录](qa/backend-baseline-20261014.json) 将历史结果与新整合检查区分。
新工作区首次检查出现 599 passed / 22 failed，增加的一项为原始文档在新 CRLF checkout 下的
校验和检查；不修改语料、批准哈希或降低门禁。最终检查另用 Git archive 的标准文件字节运行，
结果记录在整合 QA，Windows 的 POSIX 目录切换限制仍明确保留。

真实 DeepSeek 图片和 Agent 阅读／追问、真实高德商学院及浏览器 Walking 已验证；
完整联网正文仍受学校 HTTP 412 限制，Tavily 免费凭据、Jev 独立开发／保留集校准、95% 保留集目标、
真实手机相机与现场 GPS 引导尚未完成，不能据草稿 PR 宣称产品验收或发布许可。

## 本地启动与回退

在融合工作区执行 `uv sync --locked --extra api --extra vector` 安装依赖，普通应用入口沿用 README。
开发预览可运行 `scripts/preview_evidence_media.py --port 8778 --amap-env <仓库外绝对路径>`，
该预览使用明确的合成模型，可读取真实高德配置，但不向生产聊天提交消息。
真实模型与地图冒烟入口见 [后端配置](EVIDENCE_MEDIA.zh-CN.md)。

回退时选用三个独立开关关闭相应新能力；原始来源提交可追溯。尚未发布，本轮无需服务器回滚。
