# 理小龙 · CDUTdino Agent 文件包

成都理工大学公共资料与办事助手。它把“问清事项 → 查找官方依据 → 给出答复、办理清单或地图入口”串成一次任务，支持校园资料问答、找老师与地点、图片阅读及按需联网补证。

**体验入口：[cdutdino.pages.dev](https://cdutdino.pages.dev/)**。本包是从线上基线继续修复后的独立提交候选；现有网址仍运行线上基线，未切换生产。版本绑定见 [PACKAGE.json](PACKAGE.json)。

## 建议阅读顺序

1. [Agent 定义](AGENT.md)：角色、输入输出、工具权限、事实来源。
2. [架构说明](docs/architecture.md)：一张图与实际代码的对应关系。
3. [运行说明](docs/run.md)：本地启动、AI 配置、离线能力及外部依赖。

## 启动

安装 Python 3.14.7 和 uv 0.12.19，在解压后的本目录执行。Windows PowerShell 与 Linux 使用相同命令：

```sh
uv sync --locked --no-dev --extra api --extra vector
uv run --locked --no-sync python verify_agent.py
uv run --locked --no-sync python run_agent.py --offline
```

打开 **http://127.0.0.1:8766/**。首次安装需要网络下载依赖；随后离线模式可检查公开目录、来源、地点卡片和清单。离线模式明确显示模型未配置，不能替代完整 AI 回答、读图、联网和地图服务。完整 AI 运行只需按[运行说明](docs/run.md)配置自己的外部服务，再启动同一个入口。

## 建议演示

配置 AI 后依次提问“校园卡补办需要什么材料”“水上图书馆在哪里”，查看答案引用、办理清单及地点入口；有视觉模型时再上传一张不含个人信息的图片。高德配置后可打开地图与恐龙引导。模型、联网、地图未配置时页面会给出相应状态，不把占位结果当作功能成功。

## 文件导航

| 内容 | 位置 |
| --- | --- |
| 唯一推荐启动入口 | `run_agent.py` |
| 主 Agent 与提示词 | `backend/src/campuspilot/agent/` |
| 受权限约束的工具 | `backend/src/campuspilot/tools/` |
| 模型、检索、Web 与地图接入 | `backend/src/campuspilot/llm/`、`retrieval/`、`app/` |
| 当前知识与来源原文 | `data/cdut/rag/versions/kb-1d15bf97b31c0d90/` |
| 可重跑的离线包验收 | `verify_agent.py` |
| 本轮验证与已知限制 | [docs/validation.md](docs/validation.md) |
| 可选离线研究扩展 | [integrations/harness2/README.md](integrations/harness2/README.md)，默认不启用 |

包内保留一份当前知识及其哈希绑定的原文、向量索引与验收依据；这些属于可追溯运行数据。旧知识候选、重复备份、缓存、密钥、虚拟环境、历史开发日志、部署回滚包和宣传实验均不随包分发。代码子集与新增说明的来源分别记录于 `PACKAGE.json`，完整性由 `MANIFEST.json` 校验。
