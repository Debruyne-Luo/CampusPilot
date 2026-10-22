# 运行说明

## 环境与首次安装

支持 Windows 开发与 Linux 本地运行。使用 **Python 3.14.7、uv 0.12.19**，从本包根目录执行：

```sh
uv sync --locked --no-dev --extra api --extra vector
uv run --locked --no-sync python verify_agent.py
uv run --locked --no-sync python run_agent.py --offline
```

打开 http://127.0.0.1:8766/，退出用 `Ctrl+C`；端口占用可加 `--port 8770`。首次安装需要下载依赖，虚拟环境由 uv 在本地生成，不随提交包分发。后续 `--offline` 运行不调用生成模型、Jev、Search 或高德服务，能力限于已有资料与本地界面。

本版支持 Windows 自带“全部提取”。知识原文保存在 `data/knowledge.zip`，由 `knowledge_bundle.py` 在首次自检或启动时校验全部原始哈希并还原，保持原知识发布身份。Windows 还原和读取使用扩展路径，避免原文深层目录触发资源管理器限制；不要求改注册表或额外安装解压软件。不要手动展开或删除内层资源包。

## 配置完整 AI

将 `config.example.json` 复制到**包目录以外**的位置，填写自己的模型名称、HTTPS API 基址及密钥。启动器只接受模板中列出的配置项，明确读取指定文件，不自动加载不明 `.env`。

Windows PowerShell 示例：

```powershell
uv run --locked --no-sync python run_agent.py --config C:/Users/你的用户名/cdutdino-config.json
```

Linux 示例：

```sh
uv run --locked --no-sync python run_agent.py --config /home/你的用户名/cdutdino-config.json
```

也可以使用同名环境变量，直接运行 `run_agent.py`。配置文件优先于同名环境变量。不传配置且没有模型环境变量时，以明确的“模型未配置”状态运行；不会自动使用他人的密钥。

| 能力 | 必填配置 | 未配置时 |
| --- | --- | --- |
| 完整自然语言回答 | `CAMPUSPILOT_MODEL`、`CAMPUSPILOT_MODEL_BASE_URL`、`CAMPUSPILOT_MODEL_API_KEY` | 仅有来源的目录指引，响应标记 `model_not_configured` |
| 读图 | `CAMPUSPILOT_IMAGES=on`；主模型支持图片，或填写 `CAMPUSPILOT_READER*` | 没有 reader 时不宣称读图可用 |
| 地图/导航 | 高德 JS Key、安全码；路线与 POI 查询还需 `AMAP_WEB_SERVICE_KEY` | 保留公开地点列表，地图提示待配置 |
| Jev | `CAMPUSPILOT_JEV=on`、Jev Key 与模型/价格配置 | 不作 Jev 判断 |
| 联网 Search/Fetch | `CAMPUSPILOT_WEB_SEARCH=on`、证据账本目录与受支持的供应商配置 | 仅使用本地知识 |
| 向量/混合检索 | 检索模式与 Cloudflare 嵌入配置 | 默认 `lexical`，不额外调用嵌入接口 |

`CAMPUSPILOT_MODEL_BASE_URL` 是兼容 Chat Completions 的 HTTPS API 基址；模型需支持 tools 与 JSON 输出，不能只填聊天网页地址。`CAMPUSPILOT_READER` 独立配置时，需要同时填写该 reader 的基址与密钥。密钥也可用对应 `*_KEY_FILE` 指向包外绝对路径文件，不能同时填写 inline key 和 key file。

Search 默认供应商是 DeepSeek 的原生工具接口，要求主模型配置的基址为其正式接口；也可将 `CAMPUSPILOT_WEB_SEARCH_PROVIDER` 设为 `tavily` 并填写 Tavily Key 和免费计划确认。Jev、Search 共享账本时填写同一外部可写目录。每日证据预算不得超过 1 美元、100 次搜索流程；本包默认关联网，不承诺所有生成模型调用都有统一费用封顶，启用者应管理自己的模型账户限额。

## 启动器固定的提交行为

`run_agent.py` 固定使用 `phase2 + Agent loop + 当前知识目录`，不加载 Dify 旧运行路径、实验 Harness profile 或公开 lab 记录。默认词法检索、Jev/联网/读图开关关闭；可按模板启用后面三项。所有绑定 `127.0.0.1` 的本地进程只供本机访问。

本包不含生产运维配置。公开托管需要自行配置 HTTPS、反向代理、稳定工具凭据与 `PUBLIC_ORIGIN`，并测试鉴权、会话和服务限额。现有正式网址继续使用原部署；提交本包不会替换线上服务。评审结束日期尚未提供。

## 自检和常见问题

- `verify_agent.py` 校验包哈希、源码来源、知识文件、工具权限、真实 Agent 本地回路和 Web/SSE 功能；使用替身模型或无模型，不消耗 API 费用。
- 缺文件或哈希不一致：重新解压完整 ZIP，不单独删除 `raw/`、向量索引或验收文件；它们被知识发布清单绑定。
- 依赖或 Python 版本不符：先检查 `uv --version` 和 `uv python find 3.14.7`，不手动升级锁文件。
- 模型超时、密钥错误、联网配置缺失会返回错误或受限状态；查看页面状态及终端的脱敏错误，不应仅以 HTTP 200 判定问答完成。
- 清单勾选保存在浏览器本地，不代表已向学校提交；更换设备或清除浏览器数据后不保证保留。
- 真机 GPS、手机浏览器与低端设备能力未完成全面验收，详细边界见 [验证与限制](validation.md)。
