# 自动采集工具清理（2026-10-15）

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
