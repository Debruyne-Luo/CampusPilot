# 地点补查与图片前端接入交接

用户于 2026-10-14 已批准本轮功能。本工作区实现可审查代码，不包含部署、合并或真实地点覆盖验收。
后续用户批准将前后端整合到 GitHub：两侧已保存提交，在独立整合分支正式融合，详见 [整合交接](INTEGRATION.zh-CN.md)。
下文 overlay／补丁说明记录此前未提交时期的兼容验证；不再作为唯一正式代码入口。

## 接口与模块

- `POST /api/places/search`：`{query, category?}`，要求既有匿名会话、同源及 `X-CampusPilot-Request: 1`。返回 `places`、`sources`、`resolution`、`provider_status`、`message` 和 `map_pick_available`。界面不把供应商失败显示为空搜索。
- 本地精确名称、别名及教室楼栋优先。临时高德卡使用 `amap:poi:`、`transient: true`、`evidence_scope: location_only`；坐标为 GCJ02，不成为校務官方证据。
- `place-search.mjs` 管理后端搜索及旧请求取消；`navigationTarget` 使本地卡按 ID 导航、高德卡按服务返回坐标导航。`map.mjs` 增加临时卡与地图目的地选点，仍保留地图文字标签点击。
- `attachments.mjs/css` 独立扩展既有 composer；选择、粘贴、预览、移除、真实上传进度及失败重试。请求原始单张 binary，使用 `Content-Type` 与编码后的 `X-Attachment-Name`。预览 GET 通过 fetch/blob，保持会话校验。
- `ask(message, onEvent, fetchImpl, {attachmentIds, signal})` 保持前三个参数兼容，普通与 SSE 回退传同一附件引用，不传图片 Base64 或个人位置。
- 新对话必须等待 `/api/session/reset` 成功才刷新；图片发送成功后保留后端会话附件用于追问。上传失败的草稿保留供重试。
- `render.mjs` 展示高德来源、对应错误原因和独立的“联网搜索线索（待核对）”。多个临时地点保持名称相关性排序，不距离推荐或自动选中。

## 与桌面改版的合入方法

只读检查了 `D:\Projects\CampusPilot-desktop-field-notes` 的未提交状态：包含 main/map/sse/index 和桌面、路线改动。本轮没有修改该工作区。

后续合入应先复制三个新增独立模块 `attachments.mjs`、`attachments.css`、`place-search.mjs` 与测试；在桌面 index 添加附件样式，在现有 main composer 初始化附件模块，再按本工作区入口接入 `attachmentIds`、成功 `sent()`、重置 `clear()`、统一地点搜索及 `navigationTarget`。main/map/sse 必须逐段合并，保留桌面 followAnswer、未完成回复、地图视图模式、自动相机及原路由改动，不整文件覆盖。

已完成上述三方合并并生成可直接审查的 [功能补丁](patches/desktop-evidence-media.patch)，以两个工作区的共同提交 `5fd207cdd557f34aae6dc6d9736815749a206308` 为合并基线，桌面当前未提交文件为目标。补丁仅包含 6 个既有 v2 文件、3 个新增模块和 2 个测试文件，不包含桌面设计资产或后端代码。原桌面工作区执行 `git apply --check` 已通过，全程未写入该工作区。

应用前须核对 [依赖指纹](patches/desktop-evidence-media.dependencies.json) 的 `desktop_inputs`：每个存在文件的原始字节 SHA256 必须一致，标记 `ABSENT` 的新增路径必须不存在；随后再次执行 `git apply --check`。指纹不符应重新生成三方合并，不能强制应用或忽略冲突。补丁依赖本轮后端的图片、统一地点搜索和会话重置接口，不能独立部署到旧后端。

已合并的可预览资产位于本工作区 `output/desktop-integration/backend/src/campuspilot/web_assets`，完整桌面资产仅复制到忽略的输出目录，没有合入功能源码。该目录保留桌面相机、routeIntent 取消、followAnswer、未完成流式回复、工作区切换和动效，同时添加图片与地点能力。overlay 下 `tests/v2*.test.mjs` 共 55 项通过，main/map/sse Node 语法检查通过；预览和真实浏览器验收由集成负责。

对现有桌面 SSE 的信号参数合并时，保留原 signal 功能并增加附件引用参数；取消后不得回退发起第二条 chat。桌面图片预览附着在原用户气泡中，保持桌面 context 与入场动画。合入后用桌面现有 browser transport/wayfinding tests 和本轮图片测试共同验证。

## 验证与剩余验收

本轮 Node 测试覆盖图片类型/数量/大小、binary上传头与真实进度、纯图片/SSE回退引用、取消、后端地图搜索旧请求隔离、坐标导航和来源徽章；旧地图、办理清单与模块测试保持通过。Python 覆盖楼栋精确优先、未知编号、供应商类型、范围/坐标/重复过滤、单一模糊与多精确候选、超时/配额/超大响应/重定向和会话保护。

2026-10-14 已用 Playwright CLI 的独立命名浏览器 `evidence-ui-qa` 验证兼容 overlay：桌面 1440×960、手机布局 390×844。预览命令为 `scripts/preview_evidence_media.py --port 8779 --assets output/desktop-integration/backend/src/campuspilot/web_assets`，模型为明确的合成模型；高德卡、搜索延迟和上传失败测试使用浏览器临时网络模拟。该开发者浏览器验证不替代 Muse 独立发布验收。

| 场景 | 浏览器结果与证据 |
| --- | --- |
| 桌面系统文件选择与受保护预览 | POST 上传、GET 规范化预览成功，图片实际 naturalWidth=640；[截图](../output/playwright/desktop-overlay-image-draft.png) |
| 纯图片与文字追问 | SSE body 只含 message 与附件 ID，追问使用会话图片；空输入纯图片正常返回用途澄清；[截图](../output/playwright/desktop-overlay-image-answer.png) |
| E2A403 | 单独返回 E2A 卡并保留教室号，未输出楼层或电话表；桌面仍为阅读模式，没有自动切地图 |
| 移除与新对话 | 实际 DELETE 请求移除草稿；实际 POST reset 成功后刷新，旧附件 GET=404、界面草稿清空 |
| 手机布局选择与剪贴板粘贴 | 文件选择和模拟 ClipboardEvent 的 PNG 均上传并显示规范化预览；[截图](../output/playwright/mobile-overlay-choose-paste.png) |
| 上传失败重试 | 注入一次合成 503：草稿及错误保留、发送禁用；点击重试真实上传成功，发送恢复 |
| 多图与数量限制 | 两张纯图片发送成功；同次粘贴四张只接受三张，显示上限并禁用添加；[截图](../output/playwright/mobile-overlay-multimage-answer.png) |
| 地图未配置与选点提示 | 后端实际返回 not_configured，显示选点入口；底图不可用时选点显示明确提示；[截图](../output/playwright/desktop-overlay-map-unavailable.png) |
| 临时高德卡 | 合成卡显示高德来源、从这出发和带我去，保持桌面阅读模式；[截图](../output/playwright/desktop-overlay-provider-card.png) |
| 搜索竞态 | 合成旧查询延迟 650ms、新查询 10ms，最后只显示新地点；浏览器请求 body 只有 query，没有个人位置 |
| 真实商学院地点 | 使用用户指定的私密环境文件，仅进程内读取。聊天和地图搜索均返回 `amap:poi:B0FFFCLLP0`、成都理工大学二仙桥校区商学院、exact/success；[真实卡片截图](../output/playwright/desktop-real-amap-college-card.png) |
| 真实高德步行规划 | 点击带我去，选择目录东区图书馆为起点，实际 Walking 返回约 7 分钟、541 米；[真实路线截图](../output/playwright/desktop-real-amap-college-route.png) |

上述界面截图已经目视检查，无附件或卡片重叠、输入框溢出。正常流程未出现应用 JavaScript 异常；控制台的错误来自明确注入的 503 和预期旧附件 404，另有既存 iframe sandbox 提示。手机验收是桌面 Chromium 的手机 viewport 与模拟剪贴板，不能当作真实手机相机、操作系统剪贴板或国内移动网络验收。

真实高德浏览器验证使用 `--amap-env` 的进程内加载，独立命名浏览器 `amap-ui-qa`，localhost:8780 和桌面兼容 overlay。真实底图成功加载；商学院供应商 GCJ02 坐标为 `(104.146544, 30.677529)`，目录东区图书馆为 `(104.151472, 30.676143)`。观察到的 iframe `route-request` 使用目的地 `position`，未以目录 place ID 代替；实际 `/_AMapService/v3/direction/walking` 的 destination 与供应商坐标完全一致，返回约 7 分钟、541 米。

定位 API 观察计数为零，没有请求个人 GPS 或定位权限；聊天 POST 字段只有 message。密钥没有输出、保存到仓库或截图。实际供应商定位与这一条步行规划已通过，不代表现场入口、所有路线、真实手机系统相机或 GPS 前台导航已验收。校园地点仍保持地图供应商来源，未升级为官方校务事实或人工核验记录。

当前补丁包含与功能源码一致的 plan-state 失败步骤修正；输入文件指纹和原桌面 `git apply --check` 已在浏览器验收后重新核对通过。模拟失败／竞态仅验证行为，真实高德证据不依赖这些模拟。
