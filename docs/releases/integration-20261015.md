# 集成发布记录（Teal 玻璃主题＋架构审查修正）

日期：2026-10-15（Asia/Shanghai）。用户批准发布整合后的集成分支，未合并 main。

## 版本身份

| 项目 | 结果 |
| --- | --- |
| 用户入口 | https://cdutdino.pages.dev/ |
| 源码提交 | `2f2604b6fef51a8662e953632d6ebab1e14bc79b` |
| 分支 | `feat/desktop-backend-integration`（未合并 main） |
| 发布目录 | `/opt/campuspilot/releases/r-e950e1d98cfc` |
| 前端资源 ID | `0fe1e54412d4` |
| 发布文件数 | 252 |
| 知识包 | `approved-20261011b` / `kb-f08fa4fd8b583700`（未改） |
| 回滚目标 | `r-994da5858c65`（上一版本） |

## 本次内容

- 前端 Teal 可信配色＋液态玻璃主题，浅色/深色双主题（F 方案）。
- 架构审查修正：观测日志、每轮知识版本固定、统一执行边界、部分回答保护。
- 图片与证据后端、桌面交互、办理清单（此前已在集成分支）。

## 首次发布失败与修复

第一次发布以 `health_check_failed_rolled_back` 结束，线上自动回滚到 `r-994da5858c65`，
服务 `restored_healthy: true`。根因是服务器 venv 缺少 `pillow`：
新版本启动时 `attachments.py` 需要 `PIL`，而该 venv 建于依赖脚本加入 pillow 之前。

处理：在 `/opt/campuspilot/venv` 安装 `pillow 12.3.0`（与 `pyproject.toml` 的
`api` extra 约束一致），随后重发成功。`deploy/vps/02-venv-and-deps.sh` 已包含该依赖，
无需改动脚本；新建服务器按脚本执行即可。

## 发布后验证（外部访问，非服务器本地）

- 首页 `200`，引用 `/assets/v-0fe1e54412d4/`；资源 CSS 含 teal 变量、深色底、玻璃与步骤样式。
- `/api/catalog` `200`、`/api/map-config` `200`。
- 会话 `POST /api/session` `200`，`runtime_mode: phase2`，`model_configured: true`；
  `images_enabled: false`、`place_discovery_enabled: false` 为当前配置。
- 真实问答「校园卡丢了怎么补办？」：`success`，6 条引用，给出挂失与自助补卡步骤，
  费用与设备支持明确标为未知。
- 真实问答「图书馆在哪？从宿舍怎么走？」：`needs_clarification`，返回 2 个候选地点
  （东区图书馆、水上图书馆），符合多地点澄清与保留部分证据的行为。

## 未完成的验收

- 真实手机 Safari／微信内浏览器、实际 GPS 路线引导、3D 恐龙未在本轮验证。
- 联网补证仍受学校网页 HTTP 412 限制；Jev 继续默认关闭。
- 仓库 3 项 Windows 发布切换测试失败与 1 项 GBK 编码环境失败为既有问题，非本次引入。

原始发布清单：[live-20261015.manifest.json](live-20261015.manifest.json)。
