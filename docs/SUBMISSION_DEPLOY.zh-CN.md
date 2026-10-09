# 提交版部署与回滚

2026-10-07 用户完成首次安装，公网 HTTPS 已就绪：
`https://campuspilot.38-244-61-184.sslip.io`。独立外部检查以正常证书验证取得 healthz 200；
网页缺访客口令为 Basic 401，POST 工具缺 token 为 Bearer 401。
VPS 后端的两个独立聊天及真实工具回调已通过；用户确认电脑访客登录、线上底图和
两个核心查询卡片通过；手机移动网络也由用户确认通过，校园网仍待验证。
不应重复首次安装脚本。
最新官方知识及双模式/引导增量见本文末尾；以下首次安装步骤保留供历史与恢复参考。
用户此前完成只读检查：可用内存 578 MB，磁盘余量 6.2 GB，
80/443/8766 尚未监听；nginx 使用 53550，sing-box 与 Cloudflare Tunnel 在运行，必须保留。
服务器条件：Ubuntu 24 / 1 核 / 1 GB / 10 GB；
SSH 为 `root@38.244.61.184:22`；10 月 8 日专用密钥已安装并实测，后续部署不需输入密码。
用户已批准免费入口 `campuspilot.38-244-61-184.sslip.io`，不购买域名；
用户已完成高德个人认证并创建 CampusPilot Web JS API Key，凭据保留本机配置中。

## 1. 先只读核查

在项目根目录 PowerShell 执行以下命令。首次连接先核对服务商提供的主机指纹；
SSH 的密码提示不回显。不要把密码、终端认证内容或完整配置文件发到聊天。

```powershell
Get-Content -Raw deploy/preflight.sh | ssh -p 22 root@38.244.61.184 'tr -d "\r" | bash'
```

只输出系统版本、内存/磁盘、监听端口、运行服务及配置路径。将检查结果交给开发者后决定
80/443 的复用方式。已有 nginx/Caddy/网站必须保留；不能直接替换默认站点或占用其端口。
若主机内存余量不足约 400 MB 或磁盘不足 2 GB，先确定可行资源安排，不自动清理已有目录。

## 2. 域名与账号前置

免费 sslip.io 地址将名称内的 IP 解析为 VPS 地址，无需购买域名或域名实名模板。
2026-10-07 已通过公开 DNS 查询核对 A 记录为 `38.244.61.184`；
该 DNS 证据仅证明解析；随后公网 healthz、认证、Dify 预览回调与 VPS 后端聊天也已通过。
依据 [sslip.io 官方说明](https://sslip.io/)。
HTTPS 必须可用，Dify 才能回调工具。
不使用公网 HTTP 发送访客口令或工具凭据。尚无域名时继续本地验证，不宣称公网交付完成。
高德需确认用途、JS API 权限、域名限制、额度及相关服务协议；账号操作由用户完成。
JS key 会随浏览器 SDK 使用；安全码留在服务端代理。
[高德安全码官方说明](https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode)。

本机地图配置位于代码仓库之外：
`C:/Users/21207/AppData/Local/CampusPilot/amap.env`，包含 `AMAP_JS_KEY` 和
`AMAP_SECURITY_JS_CODE`。不要归档或上传此文件。项目目录中启动：

```powershell
uv run --env-file 'C:/Users/21207/AppData/Local/CampusPilot/amap.env' --locked --extra api python -m campuspilot.web
```

`--env-file` 使用正斜杠路径，避免 Windows 路径反斜杠被解析为转义字符。
浏览器仅接收 JS Key；启动 JSONP 请求通过固定代理路径，安全密钥留在后端。

独立访客口令使用 Caddy Basic Auth 的哈希（`caddy hash-password` 交互生成），
工具使用随机至少 32 字符 ASCII Bearer token，Dify 应用使用另外的 API key。
三个凭据不得复用。模板 `deploy/campuspilot.env.example` 不含可用凭据。

## 2a. 首次安装的本机入口

本机脚本 `deploy/deploy-first.ps1` 接收本次生成的发布包路径。先用 `-CheckOnly` 核对
包文件、SSH 工具和本机高德配置形状；不连接 VPS、不输出密钥值。
部署读取路径优先为代码仓库之外的 `D:/Projects/.campuspilot-private/amap.env`，
再检查用户 AppData 中的原保存位置；也可通过 `-AmapEnvPath` 显式指定。
共享工作目录下的私有目录已关闭权限继承，仅允许当前用户、SYSTEM 和管理员访问。
配置内容不进入源码包。原 AppData 文件仍用于已经启动的本机地图进程。
去掉此参数后，脚本交互读取新的网页访客口令，再通过 `scp` 上传无凭据源码包，
通过 SSH 加密标准输入传递高德配置及口令；通常需要两次输入 VPS root 密码。
不保存访客明文口令，网页用户名为 `campuspilot`，口令由用户保管。

```powershell
Set-Location D:\Projects\CampusPilot
.\deploy\deploy-first.ps1 -ArchivePath '.\release-backups\本次源码包.zip' -CheckOnly
.\deploy\deploy-first.ps1 -ArchivePath '.\release-backups\本次源码包.zip'
```

若 Windows PowerShell 提示“未进行数字签名”，脚本尚未执行。
本机已验证 Codex 所带 PowerShell 7 可在现有执行策略下运行本地脚本，无需修改全局策略：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File .\deploy\deploy-first.ps1 -ArchivePath '.\release-backups\本次源码包.zip'
```

此路径是当前本机运行时路径，不是服务器依赖。Windows PowerShell 和 PowerShell 7
各自的策略/配置不同；按微软 [执行策略说明](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_execution_policies)
先核对实际运行引擎，不永久调整 `LocalMachine` 或 `CurrentUser` 策略。

脚本在下载和安装前检查内存、磁盘、80/443/8766 与当前目录，只支持首次安装。
已有安装或端口占用时停止，不替换 nginx、sing-box、argo 或现有 Caddy。
后端使用现有独立安装脚本；HTTPS 使用独立 `campuspilot-gateway.service`、专用用户与
`/var/lib/campuspilot-gateway` 证书目录。官方 Caddy 2.11.7 静态包固定 SHA256，
先验证配置，再开启公网端口；不经过 apt 自动启动默认公开站点。
[官方静态包安装说明](https://caddyserver.com/docs/install#static-binaries)、
[官方版本](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)。

安全码仅写入服务器私有环境文件；访客口令通过 Caddy stdin 生成 bcrypt 哈希。
已有工具随机凭据继续独立使用。尚无 Dify 应用凭据时，网页如实提示 AI 尚未连接。
最后检查 HTTPS healthz、网页未授权 401 与工具未授权 401；这不代替有口令的浏览器、
高德线上域名权限、Dify 实际调用和国内网络验收。

发生部分安装或证书等待失败时，保留当前状态，先检查两个专用 systemd 单元；
不要重复首次安装或删除目录。后端首次 origin 修改前的私有备份为
`/etc/campuspilot/campuspilot.env.before_https`。HTTPS 网关的 admin API 关闭，改配置后
只重启该专用网关；不使用整机 Caddy reload。

## 3. 独立发布目录

先用 `python scripts/package_release.py` 生成不含凭据的源码包和 SHA256。
根据只读检查结果创建专用 `campuspilot` 用户，目录采用：

```text
/opt/campuspilot/releases/<release-id>/   每个版本的源码和独立 .venv
/opt/campuspilot/current                指向已启用版本的符号链接
/etc/campuspilot/campuspilot.env         0600，root 所有，真实服务凭据
```

本项目需要 Python 3.14.7，不能直接用 Ubuntu 24 的默认 Python 替代。
使用 uv 下载此版本，在发布目录执行 `uv sync --locked --extra api --no-dev`。
虚拟环境必须包含网页静态资源；先运行一次本地 healthz 与资料查询确认启动。
依赖安装后可清理**本次专用 uv 缓存**，不得清理其他应用缓存。

把 `deploy/campuspilot.service` 安装为独立 systemd 单元，配置文件在源码外填写；
设置真实 `PUBLIC_ORIGIN=https://你的域名` 和稳定工具 token。
复制单元后用 `systemd-analyze verify` 检查，确认路径与账号匹配再启动。
后端只监听 `127.0.0.1:8766`，保留单 worker；内存状态不能在多个 worker 间共享。

## 4. HTTPS 入口

首期安装脚本 `deploy/bootstrap-local.sh` 只装 loopback 后端，检查包 SHA256、逐文件 manifest、
压缩包路径和已有安装，创建专用用户与独立凭据；不改 nginx、sing-box、隧道或公网端口。
脚本需 root、现有 curl 与单独安装的 uv，参数为源码包绝对路径及本地 SHA256。
可以先通过 SSH 端口转发访问后端，域名准备好后再启用公网 HTTPS。
示例（在 VPS 终端中，先填写真实包名和 SHA256）：

```bash
curl -LsSf https://astral.sh/uv/0.12.19/install.sh -o /root/campuspilot-install-uv.sh
UV_NO_MODIFY_PATH=1 sh /root/campuspilot-install-uv.sh
bash /root/bootstrap-local.sh /root/campuspilot-release.zip YOUR_SHA256
```

uv 安装方式与版本路径依据 [官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)。
PowerShell 可用 `scp -P 22` 上传源码包和 bootstrap 脚本；复制 shell 文件后先用
`sed -i 's/\r$//' /root/bootstrap-local.sh` 只规范这份新脚本的行尾。
本机预览端口转发：`ssh -p 22 -L 8767:127.0.0.1:8766 root@38.244.61.184`，
浏览器打开 `http://localhost:8767`（仅本机转发，公网没有开放 HTTP）。

已有 Caddy 时，把 `deploy/Caddyfile.campuspilot` 作为新增站点导入现有配置。
以下是人工安装/更新路径；首次安装脚本使用上面的专用网关，不替换已有全局配置。
若已有 nginx，由其代理到本服务并实现等价访客认证；不要再启动竞争 80/443 的 Caddy。
仅在端口无人使用且资源可用时安装独立 Caddy。

Caddy 进程自己的环境需配置 `CAMPUSPILOT_DOMAIN`、`CAMPUSPILOT_VISITOR_USER`、
`CAMPUSPILOT_VISITOR_HASH`；它们不是 Python 的环境变量。以单独的 systemd drop-in
引用 0600 环境文件，保留其他 drop-in。`caddy validate` 成功后 reload。
模板使用 Caddy 2.8+ 的 `basic_auth`；参见
[认证文档](https://caddyserver.com/docs/caddyfile/directives/basic_auth)。

网页、`/api/*`、静态文件与地图代理经过访客认证；`/v1/*` 用 Python Bearer 鉴权，
不能添加访客 Basic Auth，否则 Dify 回调会失败；`/healthz` 只公开 ready。
无 CORS。Secure / HttpOnly / SameSite cookie，固定 HTTPS Origin，后端不记录访问日志。

## 5. Dify、额度与日志

连接前运行 `deploy/export-tool-token.ps1`：通过一次 SSH 只读取得现有独立工具 token，
保存到仓库外的 `D:/Projects/.campuspilot-private/tool-token.txt`。脚本不输出 token、不重置它，
本地私有目录仅允许当前用户、SYSTEM 和管理员；root 密码由用户本机输入。
不要截图或粘贴此文件内容。`-CheckOnly` 只核对本机入口，不连接服务器。

候选应用已经导入：
[CampusPilot-提交版候选](https://cloud.dify.ai/app/93481fad-37f1-4d20-9782-a5699439ea13/workflow)，
已填入 HTTPS 源站与独立工具 secret；第 4 版使用 dsv4 与经济型关键词 RAG，
已修复普通补办问法被误判为未知的分类冲突，原句和常见改写的生产 API 回归通过。
其 Dify 托管 Web App 已停用，只保留后端 API，避免出现绕过 CampusPilot 访客入口的第二个网页。
专用应用 API key 已获用户授权创建，保存在本机私有目录；VPS 后端聊天已接通。
用户随后要求接入新的模型服务商密钥，截图确认来源为 Token 算力服务平台，
提供 `http://sagalcc.cn:3002/v1` 的 OpenAI 兼容接口。后续复用该应用，不重复导入。
需要在另一个工作空间重建时，导入 `integrations/dify/CampusPilot-submission-candidate.yml`
为**新候选应用**，保留当前 RAG 应用。
重新检查模型供应商和知识库 ID，填入真实工具 HTTPS 地址和 token；查看 HTTP 节点鉴权，
试运行后发布。通过生产 API 验证输出完整 JSON envelope，再启用 `DIFY_STRUCTURED_ANSWERS=1`。
旧 RAG 应用保持 0，此模式只返回正文，不生成定位卡片。

### 模型服务商与知识检索

2026-10-07 已通过 Dify 官方 Marketplace 安装
`langgenius/openai_api_compatible` 0.0.68，模型使用 LLM / Chat Completions。
[官方配置字段](https://github.com/langgenius/dify-official-plugins/blob/main/models/openai_api_compatible/provider/openai_api_compatible.yaml)。
用户已明确接受 HTTP 明文传输及将密钥保存到 Dify。
授权 `/v1/models` 返回 200，包含 `glm-5.1` 与 `dsv4`；`glm-5.1` 上游调用返回 502，
`dsv4` 的实际调用与 Dify 保存校验通过。因此候选的两个 LLM 节点使用平台模型 ID `dsv4`，
显示名 `CampusPilot dsv4`，不把该别名推定为某个官方模型版本。
参数提取 temperature=0 / max_tokens=256；回答 temperature=0.2 / max_tokens=1024。
接口仍是 `http://sagalcc.cn:3002/v1`；同一 3002 端口的无凭据 HTTPS 检查失败，
不能仅改协议就宣称 HTTPS 可用。网页与工具继续使用 HTTPS。

本机入口 `deploy/save-model-key.ps1` 使用隐藏输入，将模型密钥保存在仓库之外的
`D:/Projects/.campuspilot-private/model-api-key.txt`，目录关闭权限继承，仅允许当前用户、
SYSTEM 和管理员访问。不读取或覆盖已有同名文件，不连接任何网络；
`-CheckOnly` 不读密钥、不改文件。旧迁移 key 不强制要求 `sk-gw-` 前缀。
这是模型服务商 key，不能使用下面的 Dify 应用 key 或工具 token 替代。

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File .\deploy\save-model-key.ps1
```

用户已通过隐藏输入保存模型 key；只读元数据检查确认文件存在、为普通文件，私有目录
关闭权限继承并仅有三条访问规则。取得明确授权后已用于模型校验和 Dify 配置；
密钥不进入网页、源码、工作流备份或截图。只切换候选工作流，保留原应用与原知识库。

Dify 的 200 条试用消息已耗尽，原高质量知识库提示 Embedding 模型不可用。
新聊天模型不替代向量化/重排服务。提交版使用独立知识库
`CampusPilot-提交版-经济检索-待核验`（`411a785a-6732-4e7f-838e-2720b19e60d9`），
经济型倒排索引，关闭节点 Rerank；关键词检索比语义检索能力有限。
语料由 `scripts/build_submission_knowledge.py` 合并原三项事务及现有补卡/五位教师公开目录，
保留官方来源和 needs_review；没有新增已核验事实。
默认每块 10 个关键词；分隔符 `\n\n`，最大 1024 字符、重叠 50 字符；
不删除 URL，知识库 Top K=3、候选节点 Top K=4。
原高质量知识库与旧应用保留，恢复使用需要独立可用的 embedding/rerank 额度。
[Dify 官方索引说明](https://github.com/langgenius/dify-docs/blob/main/en/cloud/use-dify/knowledge/create-knowledge/setting-indexing-methods.mdx)。

`integrations/dify/submission-export.yml` 是实际发布工作流的脱敏导出，环境变量值全部清空。
`scripts/build_dify_workflow.py` 从它生成可移植候选，保持实际模型/插件/知识库配置；
另一个工作空间需要重新选择该空间的知识库。原 `baseline-export.yml` 不覆盖。

候选应用专用 API key 已创建，无需重复创建。`deploy/connect-dify.ps1` 优先读取仓库外的
`D:/Projects/.campuspilot-private/dify-app-key.txt`；若不存在，会通过隐藏输入读取密钥。
不要在命令参数、聊天、截图或源码中填写真实 key。执行入口同首装脚本，使用本机 PowerShell 7：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File .\deploy\connect-dify.ps1
```

脚本通过一次 SSH 标准输入发送助手代码及凭据。服务端先用真实 Dify 生产 API 和
已安装 Python 的 envelope/关联校验验证教师结果，失败时不修改配置。
验证通过后才保存 0600 私有备份 `campuspilot.env.before_dify`，更新 Dify 三个变量，
重启本项目后端，并同时验证两个独立后端会话的补卡/教师卡片和实际工具回调。
后续失败则恢复旧配置并重启本项目服务，不修改网关和原有服务。它只支持首次连接，
已有 key 或备份时停止，不能盲目重复执行。重启后用户应刷新网页并开始新对话。
该后端检查经 loopback 执行，不代替公网访客登录、高德线上权限或国内网络验收。

2026-10-07 用户首次执行连接入口，Dify 预检查返回 `http_403`；失败发生在
环境文件备份、写入和后端重启之前。首次失败未改变 VPS 配置。
本机同一应用的生产 API 已成功。用户随后完成只读诊断：原 urllib 请求为
403 / text / cloudflare；实际后端 httpx 为 200 / JSON，结构化答案成功，均无挑战指示。
这证明同一密钥和工作流可从 VPS 正常调用；不能据此推断具体网关规则。
连接助手已改用同一 httpx 客户端及已安装虚拟环境，保持证书验证、不跟随重定向，
无需重新创建密钥或重新安装服务。用户随后执行修复入口，返回 `DIFY CONNECTED`：
生产 API 的教师 envelope 校验通过，后端两个独立会话的补卡/教师卡片与真实回调通过。
私有环境备份保留为 `campuspilot.env.before_dify`；不将它收入源码包。
连接后的外部检查仍为 HTTPS healthz 200、网页 Basic 401、工具 Bearer 401。
用户随后确认电脑公网访客登录、线上底图和两类查询卡片都能使用。
用户随后确认手机关闭 Wi-Fi 后经移动网络也能使用；此前电脑使用的是手机热点。
这些是用户手工检查结果；校园网仍待验收，真实点位和导航仍缺核验资料。
第 4 版修复仅更新现有 Dify 工作流的参数校验代码和意图提示词，复用相同应用及密钥；
VPS 自动调用已发布版本，无需重新安装、重连或重启服务。
保留独立只读诊断入口：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File .\deploy\connect-dify.ps1 -DiagnoseOnly
```

该模式通过 SSH 标准输入复用已有应用密钥，以 VPS 已安装的独立 Python 环境
分别复现原部署助手的 urllib 与后端使用的 httpx。保持正常证书校验和客户端身份，
不跟随重定向，不改代理、配置或服务。只输出状态码、响应格式、已知 API 错误码及
网关挑战指示，不输出响应正文、请求内容、密钥或会话 ID。结果不能代替后端连接验收。

每会话最多 40 次、全站滚动 24 小时默认 100 次、最多 2 个聊天同时等待；
工具独立 90 次/分钟，地图代理独立 120 次/分钟。这些计数在重启后清零，
不能代替供应商的硬费用上限；在 Dify/模型服务端设额度，预算分别记录并确保总新增费用 ≤300 元。
不会自动购买、续费或开通收费服务。

用 systemd journal 检查状态，避免调试模式、请求正文和完整异常堆栈。
在现有日志保留策略中为本单元安排限额，不直接覆盖整台机器 journald 配置。
本服务无数据库、不写聊天记录；还需核对 Dify 云端的会话保留设置。

## 6. 必要验收与回滚

### 已安装网站的地图布局更新

本次只更新网页布局。使用 `deploy/update-map-layout.ps1`，不要重复首次安装或 Dify 连接。
脚本不读高德/模型/Dify 凭据，使用现有 SSH 主机指纹和当前虚拟环境；
root 密码由用户在本机 SSH 提示中输入。`-CheckOnly` 不连接 VPS。

```powershell
Set-Location D:\Projects\CampusPilot
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File .\deploy\update-map-layout.ps1
```

更新严格限定为 `index.html`、`style.css`、`map-shell.css`、`app.js` 和地图 iframe 的三份文件。
先核对原安装包、10 月 7 日地图布局或 10 月 8 日已成功部署候选地图的静态文件哈希；
已安装同一新版时只验证，不重复改文件；发现其他修改则停止。
备份位于 `/opt/campuspilot/ui-backups/<备份ID>`，目录 0700、文件 0600；
保留原权限，每个文件原子替换，HTML 最后发布。逐文件检查 loopback 实际响应的 SHA256，
并检查公网 HTTPS healthz。失败则恢复本次替换的旧文件，移除本次新增的样式文件。
不修改环境、工作流、目录数据、代理或 systemd，不重启后端，内存对话仍保留。

成功结果为 `MAP LAYOUT UPDATED`。刷新公网网页检查新布局；浏览器缓存仍旧时使用强制刷新。
需要主动恢复旧布局时，使用成功日志中打印的备份 ID：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File .\deploy\update-map-layout.ps1 -RollbackId '实际备份ID'
```

回滚会核对备份、当前发布目录及更新后的哈希，后续已有修改时拒绝覆盖。
备份保留在私有目录中；不会删除发布目录。回滚成功结果为 `MAP LAYOUT ROLLED BACK`。

2026-10-07 用户已完成此布局更新，文件校验与公网 HTTPS healthz 通过。
旧版备份 ID：`20261007T145632Z-77f1f7b2`。外部未授权检查保持网页 Basic 401、
工具 Bearer 401，健康检查为 200/ready。无需重新连接 Dify 或开始新的后端会话。

### 已安装网站的建筑坐标候选更新

2026-10-08 的本地快照增加 14 个 `needs_review` 高德建筑坐标，详情见
[候选核对清单](MAP_CANDIDATE_REVIEW.zh-CN.md)。这不是事实批准或导航验收。
用户已部署该候选快照。下面的更新入口同时发布网页和 `places.json`；安装同一内容只验证：

```powershell
Set-Location D:\Projects\CampusPilot
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File .\deploy\update-map-layout.ps1 -IncludeMapCandidates
```

脚本不读任何本机凭据文件，SSH root 密码在本机提示中输入。更新前拒绝地点/网页的未知
修改；地点 ID、校园业务字段和关联不能变，只允许候选坐标与解释备注变化，不能自动设置
`confirmed`。地点数据在 `/opt/campuspilot/data-backups/<数据备份ID>` 私有备份，
网页在 `/opt/campuspilot/ui-backups/<网页备份ID>` 私有备份；权限分别为 0700/0600。

仅重启 `campuspilot.service` 一次以加载数据，原有 nginx、sing-box、argo 与专用网关不改。
随后核对实际网页字节、完整 `/api/places` 记录及公网 HTTPS healthz；候选不能带导航 URL。
失败自动恢复网页与数据并重新加载旧快照；重复安装同一内容只验证，不重复重启。
成功提示为 `CAMPUS MAP UPDATED`。后端重启会清空内存会话，刷新后开始新对话。
更新成功后还需实际检查公网标记、手机布局和 Dify 查询地点卡片；脚本成功不替代这些检查。

要主动回退地点数据，使用本次成功日志中的数据备份 ID；回退网页另用网页备份 ID。
两项分开执行，不能把数据 ID 传给网页参数。回退前核对当前内容未被后续编辑，失败恢复
回退前状态；数据回退会重启本项目后端，网页回退不重启。

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File .\deploy\update-map-layout.ps1 -RestoreMapCandidatesId '本次数据备份ID'
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File .\deploy\update-map-layout.ps1 -RollbackId '本次网页备份ID'
```

2026-10-08 用户执行 `-IncludeMapCandidates` 后返回 `CAMPUS MAP UPDATED`，
实际提供的网页、完整地点记录和 HTTPS healthz 验证通过。数据备份 ID 为
`20261008T023238Z-4f0c81f5`，网页备份 ID 为 `20261008T023238Z-1fb91c23`。
它们保留的是候选更新前的数据和 10 月 7 日已上线的大地图布局；不要与首次布局备份混用。
独立外部检查 HTTPS healthz ready、网页缺口令 Basic 401、工具缺 token Bearer 401；
东区图书馆、珙桐餐厅与网安楼的实时工具记录与本地快照一致，网安楼继续无坐标。
两个独立已发布 Dify API 对话返回正确地点/补办 ID，珙桐 Python 卡片解析到新候选坐标且无导航。
这不替代新版有口令的网页、手机显示与重启后内存会话手工检查。

用户随后回复“手机通过”，确认本次候选地图更新的手机检查完成。

### 简约体验更新（2026-10-08）

Dify 第 6 版短答已发布；不需要重新连接密钥或重启后端。
精简网页使用上方默认 `update-map-layout.ps1` 更新，**不加** `-IncludeMapCandidates`。
本次只发布静态文件：折叠资料说明、突出房号和步骤、取消重复提示，真实高德 POI
提供“打开高德”详情入口；地点记录、凭据、代理、systemd 和后端均不变。
更新助手已纳入实际上线候选地图的哈希，继续保留漂移拒绝、私有备份与失败恢复。
2026-10-08 已使用专用 SSH 密钥直接完成默认静态更新，返回 `MAP LAYOUT UPDATED`。
实际提供的 7 份静态文件与本机一致，公网 HTTPS healthz ready；未重启后端或改变凭据。
私有网页备份 ID：`20261008T043354Z-9c75826e`，保留本次精简前已上线的候选地图界面。
需要回退时使用默认入口的 `-RollbackId '20261008T043354Z-9c75826e'`；不涉及地点数据回退。
云端短答与精简网页均已生效，刷新网站即可。

### 一次性 SSH 密钥配置（2026-10-08）

用户选择使用专用 SSH 密钥，以便后续由 Codex 直接部署，无需保存 VPS 密码。
本机密钥已生成并验证配对，保存在仓库外 `.campuspilot-private/campuspilot-vps-ed25519`；
ACL 仅当前用户、SYSTEM 和 Administrators。`-PrepareOnly` 不连接服务器或改 SSH 配置。
使用 `deploy/enable-vps-key.ps1` 完成一次服务器安装，root 密码仅在本机 SSH 提示输入：

```powershell
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" -NoProfile -File D:\Projects\CampusPilot\deploy\enable-vps-key.ps1
```

只追加带 `restrict` 的专用公钥，保留已有 authorized_keys、密码登录和服务。
既有主机指纹仍严格校验；新密钥非交互登录通过后，才加入本机 `campuspilot-vps`
及对应 IP 的 SSH 客户端配置，已有配置先私有备份，后续并发改动不覆盖。
成功提示 `SSH KEY READY` 后现有部署入口可直接复用，不需重复输入密码。
首次用户安装在新密钥验证阶段失败，本机 SSH 配置未写入。独立只读 SSH 握手确认
服务端当前仅提供 `password`，没有提供 `publickey`；不是把该失败当成密码错误。
补充服务端助手：在已鉴权密码连接内读取 root 的有效 SSH 设置，只在现有单因素密码
策略下添加 root 密钥认证；不关闭密码、不降低多因素要求、不改其他用户或端口。
先对临时配置执行 sshd 语法及有效设置校验，变化范围仅限三个认证字段；再私有备份到
`/opt/campuspilot/ssh-backups/<ID>` 并原子写入，reload 本机 `ssh.service`，已有会话保留。
reload 失败恢复旧配置。客户端仍在真实密钥登录通过后才写别名和 IP 配置。
11 项合成配置测试覆盖单因素替代、多因素拒绝、保留密码及算法、无关有效配置变化拒绝、
语法失败不写入、reload 失败恢复和成功备份；Ruff、Python 3.12 AST 与本机配对检查通过。
用户执行修复后的入口并返回 `SSH KEY READY`，服务端认证配置私有备份 ID 为
`20261008T043313Z-8a5a75fd`。随后 Codex 实际执行 `ssh -o BatchMode=yes campuspilot-vps`
取得 root，并在无密码提示下完成精简网页部署；本机别名和对应 IP 配置均可复用。
独立检查确认后端 healthz ready、CampusPilot/专用网关/sing-box/argo 均 active，
nginx 进程仍在；可用内存约 512 MiB、磁盘余量约 5.86 GiB。这是本次运行快照，非负载测试。
VPS 密码没有保存；原有密码登录保持可用。

### 核心场景验收

- 访问口令成功和失败各一次；无 Bearer 的工具请求为 401；错误 token 不返回目录。
- 校园网、移动网络各访问一次，手机与电脑均可查询；记录时间、设备与结果。
- 两个独立浏览器会话检查隔离，聊天等待期间工具回调应仍返回，第三聊天显示限流。
- 真实高德 SDK 加载、已确认点位、外部导航；失败保留文字资料；未经确认的点不开放导航。
- 在真实 Dify 记录里检查 HTTP 结果与 Code 输出 ID 相同；未知姓名、办公室未知和同名候选。
- 重启后旧会话显示重新开对话；检查来源/日期，不能把历史假期安排当成当前规则。

保留上一版本发布目录、源码包及 DSL/语料备份。回滚时把 `current` 符号链接切回
已验证的上一目录，重启 CampusPilot 单元，不修改其他服务；访客需要开始新对话。
切回上一 Dify 应用时同时恢复 `DIFY_STRUCTURED_ANSWERS=0` 与对应 key，凭据不进入备份包。
每次切换后检查 healthz、目录、会话和工具鉴权。VPS 2026-11-04 到期，后续评审需续期。


### 站内路线与后端同步发布（2026-10-08）

本轮用户明确授权发布。新增 `deploy/publish_routes.py` 配合 `update_routes.py`，仅更新固定7个
运行文件：web.py、app.js、index.html、map-frame.js/css、journey.js/css。由开发前源码包取得
期望旧哈希，发现服务器漂移即停止；先私有备份，原子替换后重启CampusPilot后端并验证健康
与实际网页字节。失败恢复全部旧文件（新增文件则移除）并检查恢复后健康；相关回滚测试通过。
已有账户、凭据、网关、其他服务和目录数据不在更新范围内。后端重启后需要新对话。

```powershell
.venv/Scripts/python.exe deploy/publish_routes.py --baseline release-backups/campuspilot-20261008T114806Z.zip --check-only
.venv/Scripts/python.exe deploy/publish_routes.py --baseline release-backups/campuspilot-20261008T114806Z.zip
```

本次返回 `ROUTES UPDATED`，备份ID `20261008T121549Z-e2909f42`，目录
`/opt/campuspilot/route-backups/20261008T121549Z-e2909f42`，manifest记录每个文件前后哈希。
预更新本地源码包 SHA256：`0847b46b70b5abe283bff2d6fcdcdab7ffa0dd65d5b05b239792c7ac28a22b20`。
后续修改应以相应已发布源码包作为新基线，不要继续使用旧静态更新器覆盖本增量。

发布后公网健康与鉴权正常；服务器真实算路得到699米；两个独立业务查询成功。
Uvicorn服务的 `--no-access-log` 在发布前确认，现有网关同样关闭访问日志。
高德新增代理路径仅为walking和coordinate/convert，响应不缓存；精确起点不进入模型。

最终补充：手动选择结果会使在途旧查询失效，浏览器回归通过。该单行修复已同步发布；最终备份ID `20261008T122249Z-a89f4eb5`，对应上一版源码包 `campuspilot-20261008T122210Z.zip`。

### 官方知识增量（2026-10-08，已发布）

`deploy/publish_knowledge.py`复用事务式更新器，固定7个运行文件；校验会话、官方查询、
已结束状态和本地短答，失败恢复旧文件/删除新增文件。实际返回`KNOWLEDGE UPDATED`，
备份 `/opt/campuspilot/knowledge-backups/20261008T142320Z-80ef5c2f`。
发布前源码包 `campuspilot-20261008T140154Z.zip`，SHA256
`d27a9134fbd0a6a4292dd00e812faea16b3aa7fecf43729dbcc93c2a62fc13e2`。
生产检索/指南/本周空结果与教师/补卡两个Dify会话通过；公网healthz200、未授权入口401。
最初两次脚本编码/语法失败发生在文件写入前，未修改生产；改用UTF-8输入后成功。
实际VPS Python为3.14.7；仍保留发布脚本3.12语法兼容检查。

### 双模式与地图/引导增量（2026-10-08，已发布）

`deploy/publish_workspace.py`复用同一引擎，仅同步9个固定文件：web.py、index.html、
app.js、journey.js、map-frame.js/css、新workspace.css、map-discovery.js与guidance.js。
沿用严格SSH主机指纹与私钥；先备份再原子替换，重启后检查所有实际提供字节。
在回滚边界内验证知识路径及真实高德around/detail/walking，不用合成响应代替上线证据。
合成回滚测试覆盖新文件清除、旧文件恢复、健康失败和哈希漂移拒绝。

```powershell
.venv/Scripts/python.exe deploy/publish_workspace.py --baseline release-backups/campuspilot-20261008T143431Z.zip --check-only
.venv/Scripts/python.exe deploy/publish_workspace.py --baseline release-backups/campuspilot-20261008T143431Z.zip
```

发布前基线包 SHA256：`eb6de5730ef3d61b7e0b6e4845f7315e4e343a7bb59c9b4ef1bdc0a0419688f2`。
实际返回 `WORKSPACE UPDATED`，9个文件，私有备份目录
`/opt/campuspilot/workspace-backups/20261008T154314Z-5d1f1042`；manifest记录前后哈希。
先前两次发布检查因未带SDK协议参数而被高德拒绝（`USERKEY_PLAT_NOMATCH`），更新器均
恢复旧文件并确认健康。补入真实观察到的 `s=rsv3` 等JS SDK字段后，先在本地与服务器
只读验证搜索/详情/道路，再重新发布，全部语义检查通过。异常输出只包含白名单阶段代码，
不输出上游正文、会话Cookie或坐标。新增合成测试覆盖异常信息脱敏及恢复。

生产浏览器通过临时127.0.0.1测试桥接及鉴权SSH读取真实生产响应，没有复制访客口令或
改变网关。桌面/手机模拟取得攻坚楼真实步行路线792米/约11分钟；触屏tap热点可打开详情，
输入聚焦scale=1；官方指南短答和返回对话不重发通过。公网HTTPS健康/鉴权另行核验。
更新后再独立检查教师/补卡Dify会话、确定ID与缺坐标文字降级，均通过。
本轮没有切换Dify模型、修改凭据或业务目录。真机GPS/校园步行及iOS仍待下一轮实测。

### 演示稳固性与缓存策略增量（2026-10-09，已发布）

用户明确授权提交、推送与线上发布。本轮沿用 `deploy/publish_workspace.py`，固定文件清单
由 9 个增加到 **10 个**，新增此前未纳入该清单的 `web_assets/style.css`（本轮删除了其中
从未生效的孤儿规则）。其余 9 个文件不变：web.py、index.html、app.js、journey.js、
map-frame.js/css、workspace.css、map-discovery.js、guidance.js。没有新增部署工具。

```powershell
.venv/Scripts/python.exe deploy/publish_workspace.py --baseline release-backups/campuspilot-20261008T155354Z.zip --check-only
.venv/Scripts/python.exe deploy/publish_workspace.py --baseline release-backups/campuspilot-20261008T155354Z.zip
```

基线包 `campuspilot-20261008T155354Z.zip`（用户此前记录的 SHA256
`b9ee276feff45fab8030832782062023929c5115a6a8311377562de0e44f9ef0`）的 manifest 含本次全部
4 个被修改文件。发布前经只读 SSH 逐文件核对服务器实际哈希，与基线 `before` 完全一致，
无漂移；`--check-only` 返回 `WORKSPACE RELEASE CHECK OK: 10 fixed files`。

实际返回 `WORKSPACE UPDATED`，10 个文件，私有备份目录
`/opt/campuspilot/workspace-backups/20261009T092049Z-0845d0ec`。

发布后独立核验（只读 SSH + loopback，未使用访客口令）：

- 服务器工作区 4 个文件哈希与本机完全一致：web.py `5a71f814…`、app.js `3241b8be…`、
  style.css `e9bf93e5…`、index.html `9b31e812…`。
- loopback 实际提供的 `/assets/app.js`、`/assets/style.css`、`/`（index.html）字节哈希
  与上述值相同，即"工作区 = 实际提供"。
- `/assets/app.js` 响应头为 `cache-control: no-cache` 且带 ETag；`/api/catalog` 仍为
  `cache-control: no-store`，原有契约未变。
- 提供的 index.html 中 `mobile-new-chat` 出现 0 次、`send-label` 出现 1 次；
  提供的 app.js 中 `newGeneration` 出现 3 次、裸 `crypto.randomUUID()` 出现 0 次。
- 公网 `https://campuspilot.38-244-61-184.sslip.io/healthz` 为 200 `{"status":"ready"}`，
  根路径 401（Basic 网关生效）；`campuspilot.service` 与 `campuspilot-gateway.service` 均 active。

本次不涉及凭据、网关、systemd、Dify 工作流或目录数据；`data/cdut` 未变，因此
`PLACES_BASE`/`BASE` 等旧更新器基线不需要改动，`update-map-layout.ps1` 仍只用于
它自己的固定静态文件集，不要用它覆盖本增量。后端重启会清空内存会话，刷新后开始新对话。

需要回退本次增量时，按同一基线包反向使用既有发布器或从
`/opt/campuspilot/workspace-backups/20261009T092049Z-0845d0ec` 恢复；回退前先核对当前
文件未被后续编辑。当前 10 文件集的漂移拒绝与失败回滚沿用既有实现，未修改其逻辑。

