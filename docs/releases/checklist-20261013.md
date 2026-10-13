# 办理清单发布与桌面改版交接

**CONFIRMED：** 用户批准分支直接上线，保留 main；后续桌面改版从本次上线版本出发。

## 发布事实

- 功能分支：`feat/handling-checklist`。
- 应用 / Tested Commit SHA：`258ff205b73d6b2207d0234d26f04fcdec09134a`。
- 发布包：`r-994da5858c65`，前端资源 `cc200f2fc48f`。
- 正式入口：https://cdutdino.pages.dev/ 。
- 服务器返回 `RELEASED`，原子切换 current；前一版本 `r-0f1805acf68e` 保留可回滚。
- [服务器 manifest](live-20261013.manifest.json)：122 文件哈希全部匹配 Git blob。
- 相比此前部署只变更 v2 下 app.css、index.html、main.mjs、render.mjs，并新增 handling-store.mjs、handling-ui.mjs。
- 知识包 `approved-20261011b`、后端、依赖和网关配置未改。无需合并 main 才能部署。
- 打包使用 Git blob 原始字节，避免 Windows CRLF 改变既有知识包校验值。

## 验证与限制

独立发布前 QA：**PASS**，Blocking findings 无，Non-blocking findings 无。
隔离 checkout 为 `D:/Projects/CampusPilot-checklist-release`。
48 项 Node 测试通过；独立 Chromium 合成 API 覆盖跨标签页同步/撤销冲突、恶意文本、
320px 布局、未知资料、无坐标地点、配额不足和禁用存储；0 pageerror。
开发者后端网页测试 14 通过，Ruff 通过，Git 空白检查通过。
全量 pytest 被本机 Python 临时目录权限阻断；mypy 缺少 numpy 报 1 项错误，未声称通过。

发布后：正式域名真实公开测试问题“校园卡丢了怎么补办？”成功产生可加入清单。
浏览器实际加入、勾选、刷新保留、办完/撤销、新对话保留、390px 无溢出均通过；0 pageerror。
测试清单已移出，未保存生产问答正文到版本库。真实 Safari/微信和实际步行路线未验证。

回滚使用已有发布引擎的 `_switch(base, previous)` 原子切换到上述前一版本，
重启 `campuspilot` 并检查 `/healthz`、`/api/catalog`、`/api/map-config`。
网关实际服务为 `campuspilot-gateway`；不要套用通用 Caddy 安装脚本。
回滚不会主动删除同源浏览器的 `campuspilot:handling:v1` 数据。

## 桌面前端交接

- 模块：理小龙桌面网页版；目标是把“地质野外手簿 × 对页手簿”静态稿实现为真实交互。
- 交接会话：重设计理小龙桌面网页版。
- 隔离目录：`D:/Projects/CampusPilot-desktop-field-notes`；分支 `feat/desktop-field-notes`。
- 上游：本次应用提交、当前真实 API、设计资产 `docs/design/field-notes-v1/` 及 brand-v2 PNG。
- 下游：可浏览验证的前端实现、变更记录、测试结果；第二次发布在改版完成并验证后另行执行。
- 接口 / schemas：继承 [办理清单契约](../HANDLING_CHECKLIST.zh-CN.md)，存储键保持 `campuspilot:handling:v1`，保留旧清单数据。
- 允许修改：现有前端组件、样式、品牌静态资源和必要前端测试/文档。
- 禁止修改：main、其他工作树、服务器配置、知识库和模型/检索行为；不要直接用旧 main 覆盖新功能。
- 先补齐设计稿缺失的清单入口、加入状态、列表、详情、空态、完成/撤销；学生端保持精简。
- 设计已有 1440/1280 宽桌面稿，1280 以下保留现有手机体验，移动改版另行设计。
- 品牌 PNG 可用作图标和首页插画；吉祥物不是 3D 模型，不能替换地图导航模型。
- 设计示例不是学校事实；地图和业务信息必须来自现有真实数据接口。
- 草稿中的设置、取消、证据能力先核对实际支持，不能出现可点击但无实际行为的控件。
- 风险：桌面整体改版可能破坏聊天流、地图尺寸和已存清单；必须验证这些现有流程。
- 验收：1440/1280 桌面真实流程、390/320 手机回归、旧数据保留、错误/中断可恢复，无新增页面错误。
- 主线合并仍由用户决定；本交接不授权后续会话直接发布第二版。
