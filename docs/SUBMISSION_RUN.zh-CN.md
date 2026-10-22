# 理小龙：提交包运行与演示

作品：**理小龙 CDUTdino（CampusPilot）**。正式访问入口：<https://cdutdino.pages.dev/>。
提交候选和线上部署分别记录；源码提交、知识版本及包校验以交付目录中的 `VERSION.json`
和 `SHA256SUMS.txt` 为准。候选经过审阅、实际部署后才代表线上行为。

## 评委体验

无需安装即可访问正式入口。建议使用现代桌面浏览器，依次体验：

1. 询问“校园卡挂失怎么办”，阅读答复，展开引用核对官方来源与适用范围。
2. 将可办理事项加入清单，勾选一项准备材料，刷新页面检查保存与恢复。
3. 查看地点与步行参考路线，尝试恐龙引导、暂停和退出。固定起点演示不等于实际 GPS 导航。
4. 如需体验读图，上传不含个人信息的合成图片，提问后删除附件。

作品提供公开信息与只读辅助，不代登录、缴费、预约或提交校务申请。答案受资料时效和外部
模型影响，应结合引用原文核实。手机 Safari/微信、实际 GPS 和低端设备长时间性能尚需真机验证。

## 从源码 ZIP 启动

需要 **uv 0.12.19、Python 3.14.7**；源码 ZIP 启动无需 Git 历史。
解压到独立目录，从包含 `pyproject.toml` 的目录执行。首次安装需要网络：

```powershell
uv sync --locked --extra api --extra vector
uv run --offline --locked python -m campuspilot demo
```

第二条为明确使用合成资料的离线演示，不验证真实问答、联网、读图或地图服务。
启动真实知识库网页时，在 PowerShell 设置以下非敏感配置：

```powershell
$env:CAMPUSPILOT_RUNTIME_MODE = 'phase2'
$env:CAMPUSPILOT_AGENT_LOOP = 'on'
$env:CAMPUSPILOT_RETRIEVAL_MODE = 'lexical'
$env:CAMPUSPILOT_ASSET_VERSION = 'auto'
$env:CAMPUSPILOT_MODEL_BASE_URL = 'https://api.deepseek.com'
$env:CAMPUSPILOT_MODEL = 'deepseek-flash'
$env:CAMPUSPILOT_MODEL_MAX_TOKENS = '1500'
$env:CAMPUSPILOT_MODEL_KEY_FILE = 'C:/private/deepseek-key.txt'
uv run --offline --locked --extra api python -m campuspilot.web
```

本机 Windows 的默认 Proactor 事件循环曾出现 `WinError 10014`。遇到同一系统错误时，
可显式使用 Selector 事件循环启动（已在本次浏览器联调中验证）：

```powershell
uv run --offline --locked --extra api python -c "import asyncio,uvicorn; config=uvicorn.Config('campuspilot.web:app_factory',factory=True,host='127.0.0.1',port=8766); asyncio.run(uvicorn.Server(config).serve(),loop_factory=asyncio.SelectorEventLoop)"
```

将密钥文件路径换成你自己的仓库外绝对路径；文件只包含 API Key，勿把密钥写入代码或分享。
打开 <http://127.0.0.1:8766/>。保持 `CAMPUSPILOT_KNOWLEDGE_BUNDLE` 未设置，应用读取
随包携带的 `data/cdut/rag/current.json`；不要用历史 approved 包替代活动知识。
没有真实模型配置时，网页和目录检查不等于 AI 问答通过。

Linux 上运行同一组 `uv sync` 命令，并用以下环境设置替代 PowerShell 写法：

```bash
export CAMPUSPILOT_RUNTIME_MODE=phase2 CAMPUSPILOT_AGENT_LOOP=on
export CAMPUSPILOT_RETRIEVAL_MODE=lexical CAMPUSPILOT_ASSET_VERSION=auto
export CAMPUSPILOT_MODEL_BASE_URL=https://api.deepseek.com CAMPUSPILOT_MODEL=deepseek-flash
export CAMPUSPILOT_MODEL_MAX_TOKENS=1500
export CAMPUSPILOT_MODEL_KEY_FILE=/absolute/private/deepseek-key.txt
uv run --offline --locked --extra api python -m campuspilot.web
```

## 外部能力与配置

完整配置模板为 `deploy/vps/03-env.example`，实际配置留在仓库外。模板中的占位符须替换，
只有完成凭据、价格、预算和能力联调后才可将对应功能称为可用：

| 能力 | 依赖与边界 |
| --- | --- |
| 普通知识问答 | DeepSeek 文本模型；随包的活动知识、来源原件和索引 |
| 地图与步行路线 | 高德 JS Key、安全码及匹配域名；定位需要浏览器授权 |
| Jev、Search/Fetch | 单独凭据、价格和持久预算目录；保留既有支出，不重置账本 |
| 读图 | 单独的图片 reader 配置及 Gemini 凭据；不是文本模型自动具备的能力 |
| Harness² | 独立 Linux/Python 3.12 实验环境；普通网页无需安装，profile 默认留空 |

读图使用 `CAMPUSPILOT_READER`、`CAMPUSPILOT_READER_BASE_URL`、
`CAMPUSPILOT_READER_KEY_FILE` 配置独立模型，再显式启用 `CAMPUSPILOT_IMAGES=on`；
API Key 文件留在仓库外。配置模板不会自动读取，需由本地环境或部署服务注入。

Jev、联网和读图的详细配置见 [证据与图片](EVIDENCE_MEDIA.zh-CN.md)、
[模型与知识运行](RUNTIME_MIGRATION.zh-CN.md)及 [整包部署](DEPLOY_RELEASE.zh-CN.md)。
Harness² 的来源、Apache-2.0 许可与复现实验见 [比赛设计](SUBMISSION_DESIGN.zh-CN.md)
和 `integrations/harness2/NOTICE.md`。其他第三方许可随源码保留。

## 打包与部署复核

在源码解压目录构建运行包：

```powershell
uv run --offline --locked python deploy/publish_release.py --knowledge-current --output dist/runtime.tar.gz
```

工具校验 `SOURCE_MANIFEST.json` 绑定的源码字节，保留原提交身份，并拒绝缺失、修改、
新增的运行文件或身份冲突。校验文件哈希用于确认版本一致性，不代表发布者身份的数字签名。
运行包携带活动和回滚知识、向量、目录、原件及前端资源，不携带凭据或 Python 解释器。
服务器依赖必须按锁文件另行安装。生产部署、同源代理与回滚按 [部署说明](DEPLOY_RELEASE.zh-CN.md)
执行，并在最终审阅后切换；本次候选包不自动更新网站。

相关检查在 Linux/Python 3.14.7 与 Node 22 上执行；Windows 上 POSIX 原子符号链接测试
不能替代 Linux 验证。当前收尾状态与已知限制见 [收尾清单](SUBMISSION_CLOSEOUT.zh-CN.md)。
评审结束日期尚未提供，需在最终提交时补充在线维护期限。
