# 开发验证记录：截至 2026-10-09

## 办事回答修复

余额前提与入口补充：22项相关测试通过，Ruff、app.js语法检查通过。
复核2024年指南正文第27页/PDF第30页为自助补卡“余额大于20元”，并非挂失前提或工本费。
真实生产发布探针已检查短答主动包含余额要求；桌面顶部重复入口已移除，手机模式切换保留。
浏览器验证短答的“办理前”和详情的“办理前须知/准备材料”直接可见；最终静态页面/app哈希一致。
截图 `release-backups/qa/assistant-prerequisites-20261009.jpg`。

全套 Python 测试201 passed；本轮 Python 文件 Ruff 和类型检查、app.js 语法检查通过。
生产发布器实测补卡短答、官方链接、电话及三个建筑关联。浏览器经私有 SSH 回环连接
生产服务，使用真实 Dify 第7版，验证完整短答保留在对话、珙桐地图按钮、返回对话不重发、
费用追问和教师房号短答；这是生产内容验证，不替代公网访客登录验收。
云端新版7k字符文档可用，旧6.3k文档已禁用保留；经济倒排索引保持原配置。
截图 `release-backups/qa/assistant-card-20261009.jpg` 和 `assistant-knowledge-20261009.jpg`。
地点表示食堂/财务处建筑，不声称室内补卡机坐标已现场核验；当前时段/费用不套用旧假期通知。

环境：Windows、本地 Python 3.14.7、uv 0.12.19。本轮没有提交或推送。

## 最新增量：地图与步行引导（2026-10-09）

用户在本轮选择优先完善地图与步行引导。保留进入本轮时已有的
`evidence.py` / `reader_proxy` 未提交改动，未将其纳入本次运行文件发布。

真实浏览器先复现了两个缺陷：暂停后迟到的GPS错误把“已暂停”改成“权限未允许”；
继续引导重新创建进度状态，上一条步数/剩余距离消失。修复后同一复现得到
“步行引导已暂停”及 `resumePreservesProgress=true`。暂停/失败会废弃监听代号，继续
保留进度；到达和偏航连续计时从恢复后的有效定位重新开始。

路线卡片新增收起/展开；地图跟随使用实际卡片高度与单次中心调整，避免串行相机动画
把定位点藏在卡片后面。重新规划会展开卡片；地图失败停止GPS并保留文字分步指引。

| 检查 | 实际结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -q` | **193 passed**；既有Starlette/httpx弃用提示1项 |
| `node --test tests/guidance_progress.test.js` | **7 passed**；新增暂停后连续证据重置测试 |
| `.venv/Scripts/ruff.exe check .` | All checks passed |
| `.venv/Scripts/mypy.exe` | 声明范围通过，36个源文件 |
| `node --check` | 6个运行JS及新增浏览器脚本通过 |
| 浏览器回归 | Chrome + Playwright CLI，7组通过：原有路线、双模式、触屏、地点失败、查询失败、知识，以及新增引导边界 |
| `tests/browser_guidance_failures.js` | **14个场景通过**；见下方 |
| `git diff --check` | 通过；只有Windows换行提示 |

新增浏览器场景覆盖：卡片收起与定位点可见、小屏缩放、收起不重启GPS、暂停后旧错误、
恢复进度、监听ID复用、非法/过期/未来定位、定位错误重试、前后台暂停、同步定位异常、
地图失败文字降级、地图恢复不自动定位、收起时偏航重规划，以及退出后旧转换/定位/错误。
实际地图搜索、热点和道路几何由高德提供；GPS、时间及失败回调全部为合成注入。

视口覆盖360×640、390×844与桌面；保留
`output/playwright/guidance-compact-synthetic.png` 及
`guidance-compact-small-synthetic.png` 作为开发截图。未读取真实个人GPS，也未将其送至
聊天或Dify。上述开发回归不替代校园真机步行、iOS Safari、校园网络或Muse独立QA。

本轮基线提交为 `64a0591a4ebfa3175cd9fc9b3385c83d133d1fc8`，实际改动尚未提交。
发布前只读核对生产10个运行文件与该提交的内容一致（仅归一换行比较），然后保存
服务器实际字节作为带SHA256的基线；发布时仍按精确字节哈希拒绝漂移。
生产复核：10个部署文件哈希、9个实际提供的网页资源字节/`no-cache`策略及健康检查
全部通过；公网TLS、healthz 200、网页/无token工具401另行通过。使用真实HTTPS浏览器
来源、经认证SSH转发读取生产文件和API，同一组14个引导场景再次通过；该浏览器连接
不用于证明校园网络可达。GPS仍为合成注入。备份ID、复现与回退见
[部署记录](SUBMISSION_DEPLOY.zh-CN.md)。

## 最新增量：演示稳固性修复与类型检查闭环（2026-10-09）

本节为当前状态，下方 2026-10-08 及更早段落保留为历史。

### 环境恢复（本轮开始时的实际状态）

交接文档记录的验证命令当时无法执行：`.venv/pyvenv.cfg` 指向的 uv 托管解释器
`%APPDATA%\uv\python\cpython-3.14.7-windows-x86_64-none` 已被删除，
`.venv/Scripts/python.exe` 直接报 `did not find executable`。执行 `uv python install 3.14.7`
原位恢复该解释器即可，不需要重建虚拟环境，也不需要改 Python 版本。

另实测本机临时目录不可写（`PermissionError`），Python `tempfile.gettempdir()` 因此回退到
当前仓库目录，pytest 的临时根目录会落在仓库内。已在 `pyproject.toml` 增加 mypy `exclude`，
使 `mypy .` 不会去类型检查这些源码副本。

### 改动内容

1. `app.js`：`crypto.randomUUID()` 是**安全上下文专用** API。原来的顶层调用在
   `http://<局域网IP>`（手机联调常见）等非安全来源会让整页脚本在第一行抛错、界面完全失效。
   改为 `newGeneration()`：可用时仍用 `randomUUID`，否则回退到时间戳+随机串。
   该值只用于关联地图 iframe 代号，不承担安全用途。
2. `app.js`：`request()` 拆成 `send()` + `request()`。收到 401 时自动重新建立会话并重试一次
   （单进程重启会清空内存会话），不再要求用户刷新页面而丢失可见对话；非 JSON 响应体
   （网关错误页等）不再把解析异常当作面向用户的错误。
3. `app.js` + `index.html`：`showService()` 对缺失的可选字段容错
   （`audience`/`steps`/`notes`/`field_evidence`），一条记录缺字段不再中断详情面板；
   发送按钮文案改为写入 `#send-label`，不再依赖 `firstChild` 文本节点位置。
4. `index.html` + `style.css`：删除永不可见的死元素 `#mobile-new-chat` 及其孤儿规则
   `.mobile-new-chat`（CSS 选择器是类名，元素只有 id，该规则从未生效）。
5. `web.py`：`/`、`/map-view`、`/assets/*` 下发 `Cache-Control: no-cache`（要求重新验证，
   未变化仍返回 304）。前端文件名不带版本指纹，否则发布后浏览器可能继续执行旧的 `app.js`。
   `/api/*` 与 `/_AMapService/*` 继续 `no-store`，未改变已有契约。
6. `pyproject.toml`：mypy `exclude` 覆盖 pytest 临时目录、`release-backups/`、`output/` 等。
7. `tests/test_vps_key.py`、`tests/test_map_layout_update.py`：补全 29 处类型标注，
   使声明范围 `files = ["backend/src", "tests"]` 内 mypy 全部通过（此前只有窄范围命令通过）。
8. `.gitignore`：`output/playwright/` 收紧为 `output/`。

新增测试：`tests/test_web.py` 增加静态资源重新验证/API 不缓存策略检查，以及
“浏览器会话失效可被区分且可恢复”契约（旧 cookie → 401 `session_expired` →
`POST /api/session` 换发可用 cookie → 同一接口 200）。

### 检查结果

| 检查 | 结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -q` | **190 passed**（原 188，新增 2 项）；保留 Starlette/httpx 弃用提示一项 |
| `node --test tests/guidance_progress.test.js` | **6 passed** |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 91 个 Python 文件格式一致 |
| `mypy`（声明范围 backend/src + tests） | **Success，36 个源文件**（此前 2 个测试文件共 29 项标注问题） |
| `node --check` 六个前端 JS | 全部通过 |
| `git diff --check` | 通过，仅 Windows 换行提示，无空白错误 |
| 公网健康 | `https://campuspilot.38-244-61-184.sslip.io/healthz` 200 `{"status":"ready"}`；根路径 401（Basic 网关生效） |

### 浏览器证据（Chrome 无头 DOM 检查）

- 安全上下文（`http://127.0.0.1`，与线上 HTTPS 同属安全上下文）：应用正常执行，
  渲染 20 条地点行、4 张事务卡，`#place-count` = “20 个地点”，`#send-label` = “发送”，
  死元素 `mobile-new-chat` 不再出现，会话接口成功返回（`#status-text` 进入
  “官方资料可查询”分支）。
- 非安全来源 A/B（`http://172.22.64.1`，Chrome 在该来源不提供 `randomUUID`）：
  把 `app.js` 只回退那一行守卫后，**修复版**正常执行并走完三条失败路径
  （`#status-text` → “本地服务未连接”、会话/目录/地点错误文案均出现）；
  **回退版**完全未执行，`#status-text` 停留在静态初值“正在连接服务”，三条路径均未触发。
  这直接复现了被修复的故障，而不是仅做代码审阅。

### 未执行与限制

- Playwright CLI 的 6 个 `tests/browser_*.js` 本轮**未执行**：本机不存在 Playwright 运行时
  （`%LOCALAPPDATA%\ms-playwright` 缓存与 `playwright` npm 包均不存在）。
  本轮浏览器结论来自无头 DOM 检查，**不替代**原有的路由/工作空间/触屏交互回归，
  也不替代校园真机与 iOS Safari 验收。
- `mypy .`（显式传路径）还会检查 `deploy/`、`scripts/`、`integrations/`；这些目录从未在
  `[tool.mypy] files` 声明范围内，仍有 158 项既有标注问题。本轮只把声明范围修到通过，
  没有擅自扩大类型检查范围。
- 本轮未重启生产服务、未改动线上文件、未改动 `data/cdut`（该句指 A 增量当时的状态；
  随后的资料复核见下一节）。

## 2026-10-09 资料复核：两处核心事实仍无法由公开来源闭环

用户同时要求补齐网安楼与校园卡补卡/一卡通服务点。本轮做了主动检索与直连核对，
结论是**两处都无法只靠公开官方来源闭环**，因此没有新增坐标，也没有升级任何核验状态。

### 实测到的来源可用性

| 目标 | 结果 |
| --- | --- |
| `cist` / `news` / `wxc` / `gra` 的 HTML 正文页 | 直连一律 **412**（4 个 URL 实测） |
| `https://www.cdut.edu.cn/files/mapcl.pdf` | 直连 **200**，1254101 字节，SHA256 `2d354d43…` |
| 2024 年 8 月第四版学生指南 PDF | 直连 **200**，3581743 字节，SHA256 `825729937c…` |

两份 PDF 的实测哈希与仓库既有记录**完全一致**，说明文件未变化。这解释了既有记录里
`access_method=search_index` 的成因：同域 HTML 正文不可直读，静态 PDF 可以。

### 官方平面图能确认与不能确认的内容

下载单页 PDF、渲染并放大 3 倍逐条核对图例：第 15 号为“财务处、校园一卡通中心”，
第 22 号为“计算机与网络安全学院（牛津布鲁克斯学院）、生态环境学院”，第 23 号为“商学院”。
图例**不含“网安楼”**，因此该图不能把网安楼对应到任何编号建筑；图例也**不提供坐标**，
第 15 号只说明财务处与一卡通中心同栋，是线索而非房间号或点位。

期间出现过一次“该学院为第 23 号”的读法，放大核对后纠正为第 22 号；这正是本轮坚持
逐条复核而不直接采信摘要的原因。

### 数据侧改动（范围很小）

- `cdut:evidence:campus-plan`：访问方式由 `search_index` 更正为 `direct`，补充
  `source_file_sha256` 与两条限制（HTML 412 / 图例不含网安楼且无坐标）。
- `cdut:place:card-centre`、`cdut:place:network-security`：各新增一条 `notes.2`
  限制说明，`field_evidence` 指向官方平面图来源。
- **没有**新增坐标、**没有**升级核验状态、**没有**新增导航、**没有**修改教师字段。

### 检查结果

| 检查 | 结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -q` | **193 passed**（新增 3 项：data 档案的回滚/失败恢复、发布探针本地复跑） |
| `node --test tests/guidance_progress.test.js` | 6 passed |
| `ruff check .` / `format --check .` | All checks passed / 93 files formatted |
| `mypy`（声明范围） | Success，36 个源文件 |
| 快照校验 | `DirectoryRepository.load` 通过；20 地点/14 坐标/0 导航 |
| `deploy/publish_data.py --check-only` | DATA RELEASE CHECK OK：2 个固定文件，哈希、JSON 与 py3.12 语法均通过 |
| 发布探针本地复跑 | 新增测试用真实快照执行远程探针逻辑（地点数、坐标状态、新增备注、来源哈希） |

新增 `deploy/publish_data.py`：只发布 `places.json` 与 `sources.json` 两个数据文件，
复用既有事务式更新引擎（漂移拒绝、私有备份、重启、服务端语义校验、失败全量恢复）。
不沿用 `update-map-layout.ps1`，因为它的基线常量早于 2026-10-09 的静态资源发布，
会连带重发已由 `publish_workspace.py` 替换过的网页文件。

未找到清单、冲突线索与边界说明见
[来源可用性记录](research/source-access-20261009.json) 与
[地图候选核对清单](MAP_CANDIDATE_REVIEW.zh-CN.md)。**未找到不等于不存在。**

## 最新增量：官方知识、双模式与前台步行引导

2026-10-08 开发验收通过；下方此前段落保留为历史，以本节为当前状态。
实际生产运行时只读核对为 Python **3.14.7**，此前按Ubuntu自带3.12的判断已纠正；
本轮更新器及新知识/Web模块仍另外做3.12 AST兼容检查。

| 检查 | 结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -q` | **188 passed**；原Starlette/httpx弃用提示保留 |
| `node --test tests/guidance_progress.test.js` | **6 passed**；合成路段验证进度、误差、跳点、持续偏离、到达与非法输入 |
| Ruff check / format --check | 通过；90个Python文件 |
| mypy backend/src + test_routes/test_knowledge/test_route_update | 25个文件通过；全库既有两个测试文件的29项标注问题仍另列，不冒充全库通过 |
| JavaScript语法、发布前哈希与AST检查 | 通过；部署只更新固定运行文件，远端漂移停止 |
| browser_routes / browser_journey_failures | 原路线、业务歧义、缺位置、旧分类、延迟就绪、失败重试、返回历史和过期响应回归通过 |
| browser_knowledge | 6条真实官方资料、截止/历史、本科/研究生适用、官方链接和本地知识短问答通过 |
| browser_workspace | 双模式、滚动位置、不重发、目录外真实POI/路线、地图目的地；合成GPS验证导航、差精度、偏航重算、拒绝、暂停、退出和延迟转换 |
| browser_discovery_failures | 地图就绪前最新查询、旧检索/热点响应、真实重试、模式切换取消；实际阻断SDK后单独重载地图保留对话，旧iframe代号拒绝 |
| browser_touch | Chromium Android触屏模拟：原高德“攻坚楼”热点实际tap打开卡片；聚焦输入viewport scale=1 |
| 生产浏览器 | 经专用SSH读取实际生产响应；目录外攻坚楼路线792米/约11分钟，官方指南短答、模式返回不重发/恢复滚动，真实touch热点、输入scale=1；不使用网关口令副本 |
| 视口/视觉 | 1366×900、390×844、360×640检查；地图、助手、通知及步骤可读，无横向溢出 |

高德Key/代理真实查到 `B0J30CFWVF` 攻坚楼并取得详情与真实步行道路；东区图书馆到珙桐
仍返回699米/约10分钟。导航测试重用公开路线顶点作为**合成GPS**，不读取操作者位置；
该测试不证明校园真机GPS、iOS Safari、锁屏导航、入口通行或室内楼层已验收。
SDK加载被刻意阻断的测试出现预期网络错误；正常流程无页面脚本错误。

双模式增量已发布，备份 `20261008T154314Z-5d1f1042`。发布器在回滚边界内实测
around/detail/walking；8份实际静态响应逐文件SHA256与工作区一致。生产浏览器截图为
`production-workspace-desktop.png`、`production-workspace-mobile.png`、
`production-assistant-mobile.png`、`production-touch-hotspot.png`；正常流程0个控制台错误，
2个已知SDK/Canvas警告。访问口令与工具鉴权、公网证书/healthz分别经公网请求检查。
更新后王洪辉教师与校园卡补办各一个独立Dify会话通过，返回确定业务ID；房号保留为
网安楼204室，两类结果均未生成未知位置的地图目标。检查不输出对话全文或会话凭据。
前两次发布探针缺少SDK协议字段，实际拒绝码为 `USERKEY_PLAT_NOMATCH`；自动回滚成功。
先只读验证两端SDK参数兼容，再修正探针重发；不是用跳过探针来宣称上线成功。

官方知识已上线：7个运行文件、备份 `20261008T142320Z-80ef5c2f`；生产短答/时间状态及
原教师/补卡两个独立Dify会话均成功，公网healthz200、访客与知识接口缺口令401。
只收录6条资料，不声称全校通知全覆盖；当前没有实际微信文章、自动爬虫/OCR或新语义RAG。
正文日期/对象、URL、来源归属、替代链、原子导入失败与备份覆盖由知识测试验证。

同学试用、校园网与真实步行、独立Muse QA及最终视频仍需后续完成。发布实证见
[部署记录](SUBMISSION_DEPLOY.zh-CN.md)，本地图片位于 `output/playwright/`，包含合成定位的
图片以 `guidance-mobile-synthetic.png` 明确区分。

| 检查 | 结果 |
| --- | --- |
| pytest 全部现有与新增受影响测试 | 109 passed，约 5 秒；一次 Starlette/httpx 弃用提示，不影响通过 |
| mypy strict | 27 个源文件通过 |
| Ruff check / format --check | 通过，63 个 Python 文件格式一致 |
| JavaScript `node --check` | 通过 |
| shell `bash -n` | preflight 与 bootstrap 两脚本语法通过；不等于已在 VPS 执行安装 |
| git diff --check | 通过；Windows 换行转换提示，无空白错误 |
| 快照 | 4 事务、3 部门、13 来源、20 地点、5 教师，引用校验通过 |
| OpenAPI | 已从实际 FastAPI 应用导出，不含工具 token；新端点鉴权检查通过 |
| Dify 工作流 | Code 参数/实际响应 ID/封装离线执行通过；引用路径来自 cp_result，不来自 LLM |
| 桌面浏览器 | 珙桐食堂别名查询与地点详情；文字降级；教师查询正常 |
| 手机宽度 | 390×844；页面宽度与 scrollWidth 同为 375，无横向溢出；未收录教师提示正常 |
| 浏览器控制台 | 本地目录功能没有脚本错误或警告 |
| VPS 只读核查 | 用户 SSH 实测：Ubuntu 24.04.3、可用内存 578 MB、磁盘 6.2 GB；80/443/8766 未监听 |

新增关键边界包括：名字歧义不选人、跨校区关联失败、GCJ02/WGS84 与核对状态、
未知/不相关 ID 拒绝、正文中的 ID 不选卡片、模型文本和坐标无法代替结构化 envelope、
非成功响应不产生地点、两个聊天等待时工具请求仍能完成、全站额度跨会话限制、
生产 Origin/Secure cookie、旧会话失效与新对话恢复。合成测试上游回复与坐标注明测试用途，
未加入正式资料。保留原来的目录、假 Harness 与 CLI 回归。

2026-10-07 增量实测：用户完成高德个人认证、创建 Web JS API Key 并将凭据保存在仓库外。
真实 SDK 已显示成都周边街道底图；桌面与 390×844 手机宽度可见，无横向溢出。
主页面保持严格脚本 CSP；高德动态执行规则只用于同源地图 iframe（不构成跨源安全隔离）。
新增 SDK 启动代理、JSONP MIME、密钥由服务器覆盖、错误回调拒绝及主页面 CSP 边界回归；
受影响测试 26 项通过，Ruff/mypy/两份 JavaScript 语法通过。启动鉴权实测返回 OK；
仍无已核对坐标，未验证正式地图标记、点位或导航。截图位于 release-backups/qa/amap-live-*.jpg。

待实测：真实点位/导航、Linux 资源压力、校园网、同学试用。
Linux 安装与公网未授权检查的实证见下方增量记录。最终视频与提交验收尚未完成。
源码工作快照及原 RAG/候选 DSL/资料由 package_release.py 归档，manifest 标识基线提交、
未提交状态与逐文件 SHA256，不将工作快照冒充已提交 Git 版本。

2026-10-07 免费入口部署增量：用户批准 sslip.io 地址，公开 DNS 查询返回 VPS IPv4。
官方 Caddy 2.11.7 Windows 静态包经官方 SHA256 核对，用生产站点模板在
`127.0.0.1:8770` 运行临时网关；验证网页缺口令/错误口令 401、正确口令 200、
healthz 200、POST 工具缺 token/错误 token 为独立 Bearer 401。
这证明本地认证分流，不证明公网证书或 Linux 服务已启动。临时网关已关闭。
新增配置助手拒绝未批准地址、无效高德密钥形状和过短访客口令，且在文件/进程修改前拒绝。
Ubuntu 自带 Python 3.12 语法、PowerShell parser、shell bash -n、Ruff 检查通过。
首装脚本明确设置公共代码 umask 022，密钥仍保持私有 0600，避免独立服务用户无法读取解释器。
本机 -CheckOnly 不连接 VPS；实际安装仍等待用户在本机输入 SSH 密码。

2026-10-07 公网部署增量：用户终端显示专用后端和 HTTPS 网关首次安装成功，
发布目录为 `/opt/campuspilot/releases/20261007T041304Z`，已有服务未改动。
安装使用 `campuspilot-20261007T041106Z.zip`，SHA256：
`39022526413a0179b5c87c9eb842de126496567cea9014981c81ba3be7201ac0`。
随后独立外部请求以默认 CA 验证访问免费 HTTPS 入口：healthz 200/ready，
网页缺口令 401/Basic，POST 地点工具缺 token 401/Bearer。
这不证明有口令的网页、高德线上 SDK、国内网络或 Dify 已接通。
内置浏览器访问该公网地址出现客户端拦截；没有忽略警告、关闭保护或改用不安全连接。

2026-10-07 Dify 连接准备增量：新建并导入独立候选应用
`93481fad-37f1-4d20-9782-a5699439ea13`，保留原 RAG 与业务联调应用。
URL 环境变量已填入真实 HTTPS 源站，检查清单显示“所有问题均已解决”。
工具 secret 仍为空，未发布、未执行真实回调，清单通过不表示凭据或业务成功。
Code 节点改用 Python 3.10+ 兼容的异常语法；所有嵌入 Code 节点以
`ast.parse(feature_version=(3, 10))` 检查，14 项提交版受影响测试通过，
Ruff check/format 通过。该检查不替代云端运行。

2026-10-07 Dify 真实回调增量：用户通过只读 SSH 脚本取得现有工具 token，
已将其保存为候选应用 Secret 环境变量。独立公网鉴权请求返回补卡事务、王洪辉教师记录，
未收录姓名返回 empty，均为 HTTP 200；三个请求的地点列表均为空。
随后 Dify Cloud 预览两个独立对话均成功，运行链包含真实 HTTP 查询与 Code 封装：
补卡返回 `cdut:service:campus-card-replacement`；教师返回
`cdut:teacher:wang-honghui`，办公室文本为“网安楼204室”。两者均无地点 ID。
模型如实保留现时服务点、楼栋坐标与导航尚未确认的限制，没有补出坐标。
截图：`release-backups/qa/dify-card-live-20261007.jpg` 与
`release-backups/qa/dify-teacher-live-20261007.jpg`，不含密钥。
候选工作流第 1 版已发布；停用 Dify 托管 Web App，后端 API 保留。
应用 API key 已在用户明确授权后创建并保存于仓库外私有目录，VPS `/api/chat` 尚未接通。

2026-10-07 新模型接入：用户通过隐藏输入保存 Token 平台模型密钥，并明确接受
将其保存到 Dify、通过 `http://sagalcc.cn:3002/v1` 传输。私有目录关闭权限继承，
仅当前用户、SYSTEM、管理员可访问。模型 key、应用 key 与工具 token 分离。
授权 `/v1/models` 200，包含 `glm-5.1` 与 `dsv4`；前者实际调用返回 502，后者
实际 Chat Completions 200，Dify 保存校验通过。兼容插件为官方 0.0.68；
仅候选两个 LLM 切换为平台 ID `dsv4`，输出上限分别为 256、1024 tokens。
不推断别名对应的官方模型版本，不把同端口 HTTPS 检查失败扩大为整个域名无 HTTPS。

Dify 消息试用额度随后显示 200/200 已用尽，原知识库提示 Embedding 模型不可用。
新建独立 `CampusPilot-提交版-经济检索-待核验`，经济型倒排索引、关闭节点 Rerank；
原应用与知识库保留。上传源为 `CampusPilot-submission-knowledge.txt`，合并三份原语料
及已有补卡/教师公开目录；不引入坐标或已核验事实。57 个段落块已建立，文档状态可用。
关键词检索能力有限，不把它称为已恢复语义/向量检索。

试用额度为 0 时，经济检索下的补卡/教师独立预览均成功。曾观察到回答将未收录建筑
说成可定位、将目录收录方式说成现行唯一方式；已补充两项提示词约束后复测。
教师回答保留校区/现行性待确认和“暂不能定位或导航”；最终生产补卡回答未再断言
现行仅支持自助。确定性 ID 仍由实际 HTTP 结果和 Code 决定，未由模型正文提取。
候选第 3 版已发布；访问点仍为 Web App 关闭、后端 API 开启、MCP 关闭。

两个独立生产 API 请求均返回 200/success；补卡只含
`cdut:service:campus-card-replacement`，教师只含 `cdut:teacher:wang-honghui`，
均无地点 ID。两份响应通过实际 `AnswerEnvelope` 与 `resolve_cards` 校验，
RAG 引用文件均为新语料，Dify 会话互不相同；这不代替 VPS 后端会话隔离验证。
截图：`release-backups/qa/dify-dsv4-economy-published-v3-20261007.png` 与
`dify-economy-knowledge-configured-20261007.png`，不含密钥。
第 3 版实际 DSL 导出已清空全部环境变量，并检查三枚已知凭据均不在文件中。
生成器已与实际模型、插件及知识库设置同步，原 RAG 导出保留。
受影响提交版测试 14 passed；两份生成脚本及 Code 节点 Ruff 通过；连接脚本
PowerShell 7 -CheckOnly 通过。实际模型调用不等于 VPS 网页已接通。
连接助手最初完成本机检查：
PowerShell 7 -CheckOnly、Python 3.12 AST、无效凭据/可变目的地拒绝、Ruff。
首次连接随后由用户在 VPS 执行：生产 API 预检查返回 `http_403`，尚未创建 Dify
配置备份、写入环境文件或重启后端。当时尚不能把本机生产 API 成功当成 VPS 联通成功。
新增 `-DiagnoseOnly` 模式，对比 urllib / 实际后端 httpx 的正常请求；只读、不跳转、
不改变代理或 TLS 校验，不输出任意响应正文。6 项离线隐私和重定向边界测试通过，
Ruff、Python 3.12 AST、PowerShell 7 `-DiagnoseOnly -CheckOnly` 通过。
用户随后返回 VPS 只读诊断结果：urllib 为 403 / text / cloudflare，httpx 为
200 / JSON / cloudflare，`structured_answer=true`，两者均无挑战指示。
同一密钥及工作流经实际后端客户端可用，不据此猜测具体网关规则。
连接助手已统一使用 httpx 和现有虚拟环境，保留 TLS 校验、不跟随重定向；
无需新增依赖或改代理。连接与诊断共 12 项边界测试通过，Ruff 和两份测试的 mypy 通过。
用户随后执行修复入口，返回 `DIFY CONNECTED`：生产 API 的结构化教师记录通过校验，
私有 Dify 配置写入并重启本项目服务，两个独立后端会话的补卡/教师卡片与真实回调通过。
连接后独立外部请求保持默认 TLS 校验：HTTPS healthz 200/ready，网页缺访客口令
401/Basic，工具缺 token 401/Bearer。未把未授权检查当成有口令的浏览器验收。
用户随后按指引在常用浏览器检查公网网页，回复四项均通过：访客登录、地图底图、
补卡事务卡片、王洪辉办公室卡片。这是用户手工检查，不冒充独立浏览器自动化证据。
用户随后回复“手机通过”，确认关闭 Wi-Fi 后经手机移动网络检查通过；
此前电脑使用手机热点。校园网仍未验收；底图显示不等于真实点位/导航已通过。

语料 manifest 改为对实际写入字节计算 SHA256，修正 Windows CRLF 与内存 LF 的差异。
重新生成后的文档与已上传文件字节完全一致，不需重复上传；源文件和文档哈希匹配。
两个候选 DSL 均为 dsv4 / 独立经济检索、Rerank 关闭、环境变量值清空；
docs、integrations、deploy、scripts、tests 中未包含三枚已知真实凭据。

2026-10-07 普通补办问法修复：用户报告“校园卡需要补办，应该怎么做，去哪里？”
得到通用澄清。云端预览复现；意图节点同时返回 `kind=unknown` 与
`service_key=campus_card_replacement`，导致真实目录按未知事务处理。
校验节点在字段、枚举、长度和学年全部校验通过后，将明确事务键与 unknown 类型的
冲突归一为 service；补充意图提示词，区分补办和挂失。合法教师类型不改动，
未知键、额外 ID/URL 和非法学年仍拒绝，卡片继续从实际业务响应生成。
新增 8 项回归，与受影响提交版测试共 22 passed；Ruff 和新增测试 mypy 通过。
云端原句预览成功后，现有候选第 4 版发布。六个独立生产 API 对话全部通过：
原句、“校园卡丢了要补卡”、“一卡通遗失后怎么补卡？”返回真实补办事务 ID；
“校园卡怎么挂失？”返回挂失 ID；王洪辉办公室查询保留教师 ID；
“我要办事”保持 needs_clarification 且无记录 ID。
六份响应通过实际 AnswerEnvelope 和 resolve_cards 校验，会话互不相同，地点 ID 均为空；
未改变仍缺当前位置的事实。生产验证只记录受控状态和引用，不归档完整对话。
第 4 版实际导出与本机校验代码一致，模型和知识库不变；环境变量值全部清空，
便携候选同步更新。该云端修复不需要 VPS 重装、密钥变更或服务重启。
截图：`release-backups/qa/dify-card-intent-fixed-v4-20261007.png` 和
`dify-card-intent-fixed-reply-20261007.png`，不含密钥。

2026-10-07 地图主界面增量：按用户所提供的地图布局参考，将大幅高德底图放在首页，
增加顶部地点/教师/问答共用搜索、分类按钮、底部横向卡片、浮动详情和地图展开控制。
教师、事务与对话改为可关闭的面板，保留原查询和确定性卡片逻辑。
桌面 1411×871 下页面无横向或纵向溢出，地图约 1339×545；
手机 390×844 下 documentWidth=390、documentHeight=844，地图 366×580，
展开地图约 376×830。餐厅分类返回 4 项；“珙桐食堂”别名返回对应唯一地点；
卡片滑动、浮动来源详情、缩放/概览、教师查询和补卡指南均通过本地浏览器检查。
手机统一搜索发送用户原补办问法，真实 Dify 返回事务卡片，无错误消息；
没有保存完整对话，截图仅包含公开地图与目录，控制台无错误或警告。
截图：`release-backups/qa/map-core-desktop-20261007.png`、
`release-backups/qa/map-core-mobile-20261007.jpg`。

网页/提交版回归与新增静态更新边界共 33 passed；两份 JavaScript 语法、
新部署助手与测试的 Ruff、PowerShell 7 `-CheckOnly` 通过。
更新助手覆盖路径/校验和/体积拒绝、旧版漂移拒绝、失败恢复、新文件移除、幂等更新、
手动回滚及后续改动保护；测试文件均为明确合成内容。
助手只改 7 份已知静态文件，不读密钥、不重启服务，先私有备份再校验实际提供的字节。
用户随后执行更新入口，返回 `MAP LAYOUT UPDATED`，实际静态文件字节校验和公网
HTTPS healthz 通过；没有重启后端或改变凭据。私有旧版备份：
`/opt/campuspilot/ui-backups/20261007T145632Z-77f1f7b2`。
随后独立外部请求确认 healthz 200/ready、网页缺口令 401/Basic、工具缺 token 401/Bearer。
这是公网更新与访问保护证据；新版布局的有口令公网浏览器显示仍由用户刷新查看。

2026-10-08 建筑候选增量：使用高德官方 AMap GUI CLI 1.0.3 查询真实 POI，
保留公开字段的 20 组查询返回记录；导入 14 个 GCJ02 建筑候选，状态均为 needs_review。
20 个原地点 ID、业务字段、教师及事务关联不变；网安楼与补卡服务点不挂靠模糊 POI。
高德查询工具随后已停止，生产依赖没有增加；查询凭据不进入公开数据。
详细来源、排除项与记录在 [地图候选核对清单](MAP_CANDIDATE_REVIEW.zh-CN.md)。

目录/网页/提交版/更新助手 67 项受影响测试通过。随后新增 7 项更新边界测试，
与提交版及更新助手一起执行共 28 passed：禁止业务字段和 ID 改动、不能自动确认导航、
更新前漂移拒绝、失败恢复网页及数据、幂等不重复重启、主动数据回退及后续编辑保护。
各项涉及明确合成副本；测试结果不表示地点事实已经核验。
新增导入器、更新助手和测试 Ruff check 通过；两份 JavaScript 语法检查通过；
PowerShell 7 的候选更新和数据回退 `-CheckOnly` 通过，未连接 VPS。

本地实际 HTTP 快照 200，返回 20 个地点、14 个坐标候选、0 个导航 URL；
完整规范化记录与本地 JSON 相同。真实高德标记显示、餐厅分类和珙桐食堂别名筛选通过。
地图标记使用紧凑虚线图标，名称在聚焦/选中时显示；SDK 会克隆 DOM，
已将选择事件委托至实际渲染按钮。键盘 Enter 与鼠标点击均打开对应来源详情，
同一地点的底部卡片保持选中；没有从模型正文或绘制坐标反推记录 ID。

本轮浏览器 viewport 控制没有应用预期的 390×844，实际 DOM 与截图宽度为 1366，
因此仅记为桌面实测，手机布局复测仍待实际设备检查。既往手机通过是 10 月 7 日版本，
不能算成本次坐标与标记更新的验收。桌面截图：
`release-backups/qa/map-candidates-desktop-20261008.png`。
上述本地检查完成时尚未部署；实际部署与更新后 API 检查见下方记录。

2026-10-08 候选地图上线：用户执行已准备的更新助手，返回 `CAMPUS MAP UPDATED`。
完整地点快照、实际网页字节及公网 HTTPS healthz 通过；仅重启本项目后端，凭据不变。
数据备份：`/opt/campuspilot/data-backups/20261008T023238Z-4f0c81f5`；
网页备份：`/opt/campuspilot/ui-backups/20261008T023238Z-1fb91c23`。
独立外部请求保持默认 CA、拒绝跳转且不使用本机环境代理：healthz 200/ready，
缺访客口令网页 401/Basic，缺工具 token 请求 401/Bearer。
实时鉴权工具抽验东区图书馆、珙桐餐厅、网安楼，完整规范化记录均与本地快照相同；
前两项有待核验坐标，网安楼仍无坐标，没有把学院 POI 当成办公室。

两个独立已发布 Dify API 对话均 200/success：珙桐餐厅位置查询返回
`cdut:place:gongtong-dining`，普通补办原句返回 `cdut:service:campus-card-replacement`。
ID 与同一时段真实 VPS 查询结果一致；实际 `AnswerEnvelope` 与 `resolve_cards` 校验通过，
珙桐卡片坐标与 VPS 返回值相同、导航 URL 为空；补办未返回任何地点，两个 Dify 会话不同。
仅记录受控结果与公开 ID，不归档完整对话。这证明生产工具和 Dify ID 联通，
不冒充重启后实际网页 `/api/chat` 或手机布局验收。用户随后回复“手机通过”，
本次候选地图更新的手机检查已完成；该用户检查不等于本轮精简网页已上线。

2026-10-08 简约体验：用户要求比赛演示优先关注操作体验，减少解释性文字。
本地网页取消重复 notice、徽标、缺字段段落和地图说明遮罩；来源/年代/长备注默认折叠。
教师房号突出，指南先展示步骤，实际适用条件仍保留；历史版本说明收进详情。
助手仅用 DOM textContent/strong 渲染简短正文，不解析 HTML 或从正文生成卡片位置。
真实高德 POI 详情链接来自已收录坐标的 provider source_url，不自动确认数据或导航。

Dify 第 5 版短答发布后的实测发现补卡回答错误引导不存在的地点卡片，提示词追加
仅在 places 非空时提供地点卡片指引；修正后的第 6 版已发布。
三个独立本地后端 `/api/chat` 会话均经生产 Dify 和真实 VPS 工具成功，
补卡原句 82 字、王洪辉办公室 11 字、珙桐地点 25 字，均返回对应实际记录 ID，
未重复人工核验提醒；无地点时不再指向地点卡片。没有归档完整聊天记录。
实际第 6 版 UI 导出确认提示词与本机一致，最大输出 512 tokens；环境值清空，
便携候选同步，五枚已知密钥不在导出内。

网页、提交版契约与更新助手 40 passed；Ruff、两份 JavaScript 语法和
PowerShell 7 默认静态更新 `-CheckOnly` 通过。实际 Oct8 候选地图基线的七个哈希
与既有源码备份逐字节匹配，新增基线继续适用旧版本回退与未知漂移拒绝。
本地浏览器地点详情、POI 入口、教师房号与折叠说明检查通过；截图
`release-backups/qa/ux-simple-map-20261008.png`，Dify 发布记录截图
`release-backups/qa/dify-short-answer-v6-20261008.png`。

2026-10-08 专用 SSH 密钥与精简网页上线：用户返回 `SSH KEY READY`，服务端配置备份
`/opt/campuspilot/ssh-backups/20261008T043313Z-8a5a75fd`。Codex 随后以 BatchMode
实际登录为 root，无密码提示执行默认静态更新，返回 `MAP LAYOUT UPDATED`。
更新助手验证七份实际静态文件与本机字节一致、公网 HTTPS healthz ready；后端未重启，
凭据和地点快照未改。旧版网页备份：`/opt/campuspilot/ui-backups/20261008T043354Z-9c75826e`。
独立外部正常 CA、拒绝跳转、无环境代理请求确认 healthz 200/ready、网页缺口令
401/Basic、POST `/v1/directory/assist` 缺 token 401/Bearer。
后端 loopback healthz 200/ready；CampusPilot、专用网关、sing-box、argo 均 active，
nginx 进程仍在。可用内存约 512 MiB、磁盘余量约 5.86 GiB；没有把快照当作压力测试。
本次没有重复用户手机或校园网检查，静态字节一致证明已发布本地预览版本。


## 2026-10-08 站内步行参考路线与查询联动

用户在本轮明确批准实施计划；候选点可用于站内参考路线，外部导航确认条件保持独立。

- `.venv/Scripts/python.exe -m pytest -q`：166 passed（现有 Starlette/httpx 弃用提示一项）。
- `ruff check .`：通过。`mypy backend/src tests/test_routes.py tests/test_route_update.py`：23个文件通过。
- 全库 `mypy`：29项既有缺少类型标注的问题，集中在 `test_vps_key.py` 和 `test_map_layout_update.py`；没有声称全库通过。
- Node语法检查覆盖 app.js、journey.js、map-frame.js。新增代理测试覆盖坐标、JSONP、非法参数、固定上游、禁止缓存和状态透传；新增临时目录测试覆盖老师关联与事务多地点。
- Playwright CLI 执行 `tests/browser_routes.js` 和 `tests/browser_journey_failures.js` 通过：桌面1366×900、手机视口390×844、真实路线/分步指引、地图点选、定位拒绝、退出清除、旧分类、未知办公室、多教师共楼、过期回调、地图延迟、返回对话不重发、补卡无位置、无路线及重试。
- 真实SDK使用现有JS Key，东区图书馆→珙桐餐厅返回699米、8段指引，页面约10分钟。GPS→GCJ02转换用测试坐标单独验证；没有采集操作人的真实位置。
- 截图保存在 `output/playwright/route-desktop.png` 和 `route-mobile.png`，均为公开校园路线，不含真实会话或个人位置；不会进入源码包。
- 生产算路代理复核：HTTP 200，高德10000，699米，no-store。教师/补卡两个独立生产后端会话都返回HTTP 200、result_status=success，分别含1教师/1事务、0地点。
- 公网健康200；网页、目录、地图代理未授权401 Basic；工具未授权401 Bearer。
- 已部署7个文件与实际提供的网页字节一致。浏览器端完整流程是在本机服务检查，生产通过SSH执行后端复核；不把SSH通道浏览器尝试当作公网登录验收。
- 手机真机GPS、校园网、本轮独立Muse QA尚未复测；开发验证不替代这些项目。

最终补充：手动选择结果会使在途旧查询失效，浏览器回归通过。该单行修复已同步发布；最终备份ID `20261008T122249Z-a89f4eb5`，对应上一版源码包 `campuspilot-20261008T122210Z.zip`。
