# 自动采集工具清理（2026-10-15）

> 最新清理状态：重新出现的两份采集入口和专属测试已再次移入回收站；
> 隔离环境与 `.crawl4ai` 缓存仍不存在。正式卸载 `chrome@openai-bundled` 已成功，
> 复核本机连接桥注册项、JSON 清单及宿主程序均不存在。
> Chrome 商店版 ChatGPT 扩展仍安装并禁用，需要用户在浏览器扩展管理页手动移除。
> 下方保留各次检查的时间顺序；ChatGPT 故障仍未证实修复。

用户要求检查 Chrome 报错并清理此前配置的自动采集工具。清理使用回收站，未清空回收站；
已从原位置移除，可由用户恢复。直接永久删除命令被自动审批拒绝，改用可恢复方式完成。

## 已清理

- `D:/Projects/CampusPilot-integration/output/official-tools`：隔离 Python 环境，含
  DrissionPage 4.1.1.4、Crawl4AI 0.9.4、Playwright 1.64.0、32 个实验浏览器配置根目录，
  以及实验缓存和临时产物；25,243 文件、1,301,126,973 字节。
- `C:/Users/21207/.crawl4ai`：本轮创建的采集缓存，1 文件、16,384 字节。
- 专用入口 `scripts/probe_official_collectors.py`、`scripts/package_official_captures.py`，
  及专属测试 `tests/test_official_collectors.py`。
- `output/annotate_official_round.py`、`output/embed_official_round.py`、
  `output/verify_official_round.py`：本轮一次性执行辅助脚本。

执行前验证了绝对路径、目标归属、目录内无重解析点，并确认没有正在运行的本轮采集进程。
执行后检查原路径不再存在。没有删除共享 Python、Chrome 或 Edge 程序。

## 保留

- 用户保存的 `cdut-pages` 网页；所有已归档的官方正文、PDF、XLSX 和图片。
- `data/cdut/rag` 的采集包、批准包、成功版本、原文关系、索引和审计记录。
- 离线网页导入、栏目离线解析、条款校验、知识编译及发布命令。
- 应用 `.venv` 和维护依赖。其依赖中没有 DrissionPage、Crawl4AI、Playwright。
- 全局 `ms-playwright` 为本轮之前已存在的共享组件，未因名称相同而删除。
- 其他任务的代码和输出，以及用户日常 Chrome 资料、Cookie、密码、书签和扩展数据。

## Chrome 检查的事实与限制

本轮采集主要运行系统 `C:/Program Files/Google/Chrome/Application/chrome.exe`，
脚本使用独立临时资料目录；此前也通过已有浏览器控制连接操作过日常 Chrome。
检查时普通 Chrome 主进程没有自动化、无界面、远程调试、加载扩展或代理启动参数，
没有本轮采集进程。未发现 Chrome 用户或机器策略覆盖配置，未修改系统代理或 DNS。

已有 OpenAI 浏览器控制扩展“ChatGPT”，描述为“Control your browser with ChatGPT.”，
ID `hehggadaopoacecdllhhajmbjkdcmajg`，版本 `1.26.901.11451`。
安装记录早于本轮采集，不是此次安装采集库所新增。
其静态代码包含 `local-chatgpt:` 会话前缀，并给受控标签请求增加浏览器代理标识。
这与截图的本地会话路由有关联，但尚未证实它就是 `Model not found` 的根因。

用户已关闭扩展并报告仍然报错。浏览器工具拒绝访问 `chrome://extensions`，
没有绕过策略、修改 Chrome 的偏好文件或代用户卸载扩展。
该扩展的彻底卸载需要用户在已经打开的扩展管理页点击“移除”；禁用与卸载应分别记录。

待验证的最小对照：保持扩展关闭，彻底关闭受影响的 ChatGPT 标签，从地址栏重新打开
`https://chatgpt.com/`，不复用 `local-chatgpt:` 会话地址。必要时用户在 Chrome 访客资料
中手动登录同一账号，与 Edge 同账号新会话对照。普通重装 Chrome 不保证清除用户资料，
因此尚无证据支持把重装程序当作修复。
未禁用 CSP、证书校验或浏览器安全机制。截图中的 CSP/弃用警告不能单独解释模型错误。

用户随后报告 Chrome 访客窗口正常，截图也显示真实回复及普通服务器会话地址，
说明 Chrome 程序与当前网络至少存在可正常运行的配置。最新普通窗口截图与成功访客
截图均显示同一账号名称，原先可见的账号差异已消除；未读取账号凭据或登录数据。
普通窗口仍报 `Model not found`，地址仍为 `local-chatgpt:` 本地会话路由，尚未证实修复。
排查范围优先放在原资料的页面/会话状态及扩展影响，暂不建议重装程序。

下一步保持浏览器控制扩展关闭，关闭原 ChatGPT 标签，由用户仅删除 `chatgpt.com`
的网站数据，再从主页重新登录并新建会话。此操作会退出该网站登录并清除其本地状态，
不要求清空整个浏览器数据。此步骤尚未执行或验证，不能报告问题已经解决。

## 后续诊断更新：首轮与续聊对照

用户进一步报告 Chrome 访客也会首轮成功、第二轮失败，并提供常规服务器 UUID 会话
地址下第二轮 `Model not found` 的截图。因此，单轮访客成功不足以将问题定位到原
Chrome 资料；`local-chatgpt:` 地址也不是故障的必要条件。先前的站点数据建议暂停，
不再把缓存、浏览器控制扩展或安装损坏当作已确认根因。

用户最初回答 Edge 也在第二或第三轮失败，随后明确更正“edge可以”，并提供同一会话
连续三轮 `hello`、数字 2、数字 3 均成功的截图。以最新更正及截图为准。此结果降低了
账号整体不可用和共同网络完全不可用的可能性，但仍不能排除按客户端区分的请求路径。
本机只读版本检查：Chrome `155.0.8059.40`，Edge `155.0.4283.45`；没有修改设置或启动浏览器。

仅在扩展自带公开客户端脚本中发现可检验的模型选择差异：选模型时可以优先采用会话
metadata 的 `default_model_slug`，提交时将所选 `model` 写入请求；成功首轮后续聊会
携带服务端会话关系。这支持“首轮绑定后续聊选用了不可用模型”的待验证假设，不能
证明 Chrome 访客官网实际执行了同一脚本或同一缺陷。没有读取用户站点存储、令牌或
模型偏好值，也没有取得失败请求。

下一步最小证据为成功首轮及失败续聊的 `model`，以及失败请求状态码和错误 code/message。
不需要原始会话 ID、消息正文、Cookie、Authorization、验证令牌或完整 HAR。现阶段
根因和修复均未确认，不应宣称重装、清缓存或卸载扩展能够解决。

### 已取得失败请求证据

用户随后提供 DevTools 截图：`POST /backend-api/f/conversation` 返回 HTTP 404，
响应正文为 `{"detail":"Model not found"}`。同一失败请求的 `model` 为
`gpt-6-thinking`，`client_contextual_info.app_surface` 为 `codex_browser`，
`app_name` 为 `chatgpt.com`。仅记录必要字段，不保存截图中消息关系 ID。

这确认该请求所选择的模型在该请求上下文中被拒绝；尚不能判断该模型是否全局停用、
对账号不可用，还是客户端选择与服务端路由不匹配。成功首轮与 Edge 的实际请求模型
仍未取得。`codex_browser` 是客户端自报字段，不能单凭它证明扩展仍在运行。
下一步通过可见模型选择器重新选择当前可用模型并连续三轮验证；若选择器只显示思考
强度或没有模型，读取用户当前 `models` 请求响应中的可用模型标识后再决定，不编造
可选项、不手工篡改请求、不读取 Cookie 或本地模型偏好。问题尚未证实修复。

## 用户要求的变更追溯复查

本次仅进行只读核查，没有启动/控制浏览器、运行采集、修改浏览器资料或注册表。
范围为本会话及 `collector_experiments` 的工具调用、现有采集源码及 Git 版本、当前
Chrome/Edge 启动参数与策略、相关扩展安全字段、本机连接桥、系统网络配置和目标路径。
未读取 Cookie、浏览历史、登录凭据或站点存储。

- **已确认操作过日常 Chrome。** 根会话日志第 57、66 行实际执行
  `cua.createBrowserTab('chrome', 官方页面)`，第 340、498、820 行连接已登录砚湖页面。
  不能把全部浏览器操作描述为独立临时配置。10 月 15 日北京时间 10:22:05–10:22:13
  也重新连接过浏览器以检查故障；扩展管理页访问随后被安全策略拒绝。
- **隔离采集脚本没有发现直接改写日常资料的代码路径。** 当前源码与 Git `43633f8`
  相同。DrissionPage 使用 `ChromiumOptions(read_file=False)`、临时目录、`auto_port()`
  及禁用扩展参数；Crawl4AI 关闭持久上下文、使用隔离上下文。系统代理只通过
  `OpenKey`/`QueryValueEx` 读取；直连模式参数只作用于创建的采集进程。
  已核对的历史工具调用未发现写 Chrome Preferences/Secure Preferences、代理策略、
  DNS 或 hosts 的命令。源码和已审日志均不能替代操作前后完整快照。
- **当前 Chrome/Edge 主进程没有相关覆盖参数或策略。** 未发现自动化、远程调试、
  指定资料目录、加载扩展或代理启动参数；相关 HKCU/HKLM Policies 不存在。
  未发现本轮采集进程。系统代理仍为 `127.0.0.1:7897`，端口由 Clash Verge 的
  `verge-mihomo.exe` 监听；相关域名 hosts 覆盖为零。本次未修改这些配置。
- **浏览器控制组件仍有保留。** Chrome ChatGPT 扩展的 `disable_reasons:[1]`
  与用户禁用一致；安装/更新记录早于本轮采集。Native Messaging 注册及清单仍在，
  最后写入为北京时间 10 月 15 日 08:41:30。根会话在 08:35–08:50 没有工具调用，
  不能据写入时间归因于本线程，也不能排除桌面应用自动注册/恢复集成的影响。
  Edge 未找到对应扩展配置或连接桥。这些差异需要保留为疑点，并非已确认根因。
- **清理现状已变化。** `probe_official_collectors.py`、
  `package_official_captures.py`、`tests/test_official_collectors.py` 当前重新存在，
  创建/最后写入均为北京时间 10 月 15 日 14:20:13，与 Git `43633f8` 无内容差异。
  probe 的大小差异完全由 CRLF/LF 换行解释。不能据时间戳确定恢复者或恢复动作；
  未擅自删除这些已跟踪文件。`output/official-tools` 与 `.crawl4ai` 仍不存在。

结论：没有找到“自动采集脚本直接改坏日常 Chrome 配置”的证据；确实使用过日常
Chrome 的浏览器控制集成，其对受控标签的影响尚不能排除。当前已确认的直接失败是
请求 `gpt-6-thinking` 被该请求上下文以 404 拒绝。尚未证明为何选中该模型或与集成
是否有因果关系，不应声称完全与此前操作无关，也不能声称已经定位或修复。

追溯来源（仅必要工具调用行，不复制日志中的其他内容）：

- `C:/Users/21207/.codex/sessions/2026/10/14/rollout-2026-10-14T14-06-15-01a13904-c393-7542-911f-d2f947fb3b02.jsonl`：57、66、340、498、820、2200–2210、2263–2266 行。
- `C:/Users/21207/.codex/sessions/2026/10/14/rollout-2026-10-14T14-55-47-01a13932-1c10-7b30-b16f-848ae7b49492.jsonl`：105、112、130、181、217、305 行。

## 再次清理的实际执行结果

用户追问清理状态后，按此前明确的清理授权执行，而非仅作检查：

- 使用正式插件管理入口卸载 `chrome`，返回 `status: uninstalled`，
  插件 ID 为 `chrome@openai-bundled`。
- 独立只读复核：`HKCU/Software/Google/Chrome/NativeMessagingHosts/com.openai.codexextension`
  注册项、`AppData/Local/OpenAI/extension/com.openai.codexextension.json`、原插件
  `extension-host/windows/x64/extension-host.exe` 均不存在；未发现相关宿主进程。
- 对已确认恢复且与 Git 内容相同的两份专用采集入口和专属测试，核对绝对路径在工作区
  内、类型为普通文件后再次 `SendToRecycleBin`。三份共 49,212 字节，执行后原路径均
  不存在。未清空回收站，未提交这些删除。
- 复核先前全部八个清理目标的原路径均不存在，知识库 `current.json` 清理前后 SHA256
  相同；没有修改 Chrome 个人资料、其他扩展、系统代理/DNS 或知识内容。
- Chrome 商店版 ChatGPT 扩展仍有配置及安装目录，保持 `disable_reasons:[1]`。
  正式插件卸载没有移除它；没有通过文件或注册表绕过浏览器管理限制去删除。
  用户仍需在 Chrome 扩展管理页选择“移除”。此残留须明确报告，不能宣称全部清空。

仅验证清理状态，没有重新运行浏览器或用账号发送测试消息，ChatGPT 是否恢复仍未验证。

## 同日外部案例核查与诊断纠正

用户报告恢复 Google/Chrome 同步后复现，随后按可见确认框重置 Chrome 设置仍失败。
“恢复同步后复现”只能作为触发关联，不能确认同步配置就是根因。此前将它表述为已确定
原因过强，现予纠正。停止反复重装、重置、删除用户资料。

2026 年 10 月 15 日只读核查下列第一手报告，未发帖、未提交用户资料、未操作浏览器：

- [openai/codex #54197](https://github.com/openai/codex/issues/54197)：同一路径
  `/backend-api/f/conversation`、HTTP 404、相同错误正文及 `codex_browser` 字段。
  发帖者报告清站点数据、全新资料、重装等无效，普通 Chat 与 Work/移动端结果存在差异。
  载荷模型与本案并非完全相同，不能认定同一根因。
- [UA 对照评论](https://github.com/openai/codex/issues/54197#issuecomment-6188819821)：
  普通用户报告 Chrome/Edge 155 失败、Chromium 148 可用；只通过 DevTools 临时覆盖
  User-Agent，保留请求体不变后恢复。与本机 Chrome 155 的版本条件吻合，仍需本机验证。
- [同日 Reddit 报告](https://www.reddit.com/r/ChatGPT/comments/1x64mft/model_not_found/)：
  多人报告相似故障；手机模拟有人成功，有人失败或仅首轮有效，不能当作可靠修复。
- [Chrome 官方 DevTools 说明](https://developer.chrome.com/docs/devtools/device-mode/override-user-agent?hl=zh-cn)：
  Network conditions 可临时覆盖当前页面 User-Agent 并刷新验证，改变的是向网站报告的
  浏览器标识，不是安装旧版本。若试验失败，恢复 Use browser default 后刷新即可。

所查 GitHub 问题仍为 Open，未见维护者确认根因或给出修复版本；自动标签不算官方确认。
官方状态页当前可见的是与聊天使用无关的 Compliance Costs 数据延迟，未发现本次错误的
对应事故条目。更合理的待验证方向是特定网页客户端/浏览器标识与模型路由的兼容差异，
不是已证明的账号同步损坏。社区办法仅建议作单次、可撤销、当前标签的受控实验，
不重新安装自动化工具、不改全局快捷方式、不降级浏览器、不安装时区或 UA 扩展。
尚未在用户机器验证此办法，问题仍未报告修复。
