# 桌面与后端整合：固定提交 QA

日期：2026-10-14。**Tested Commit SHA：`893abcb062253f66d5a91e5b199db49d96903371`**。
本报告审核已提交的整合代码，不代表已部署、已合并或保留集验收完成。
后端来源提交为 `3c0c395b428496cd057557f00739a4aacd8b018e`，桌面来源为
`f3dc8edbde76fe8538f3b3873a6a62b1c4b37c25`；旧 [工作区 QA](EVIDENCE_MEDIA_QA.zh-CN.md)
属于合入前的历史截面，不应替代本报告的提交绑定。

## 结论与独立性

**PASS：本次针对性检查未发现阻塞整合缺陷。** 实测“商学院”地图／普通聊天／SSE 一致，
图片与会话边界、旧地图及网页契约通过；资产打包与版本化访问完整。
尚未取得学校受保护页面的完整联网正文，也未完成 Tavily 免费真实回退、95% 保留集或真机现场引导验收。

审查者实现过 `web_evidence`、Jev 与预算模块。因此其中 58 项是开发回归，
其余 172 项为对其他实现者的整合、附件、图片任务、Agent 与地图／网页兼容检查。
这些测试与代码审查在固定提交的独立归档目录执行，没有修改核心代码。
不重复主集成方的全量测试、Ruff 或 mypy，不将其他人的结果称为本审查者独立执行。

## 隔离环境与检查

使用 `git -c core.autocrlf=false archive` 导出固定提交到仓库外临时目录，使用 Python 3.14.7
实际解释器和现有项目依赖。导出样题 `evaluation/runtime-migration/cases.jsonl` 与 Git blob 字节相同，
CRLF 数为零；SHA256 为 `040fa373c4b8d61f697a3d00350394d65917e00fde4ccc33ecad5b692266ab2e`。
这是恢复版本控制的原始字节，未改语料、哈希或校验规则。

**230 passed / 0 failed / 0 errors**，十个测试文件：

- 图片任务 48、后端整合 36、地点补查 13、附件 17、Agent 39、网页 14、地图兼容 5。
- 联网模块 30、Jev 插件 18、Jev 接口 10；以上 58 项不声称实现者之外的独立 QA。
- 另单独执行批准知识导入原始文件／正文哈希检查，1 项通过；未重复计入 230。
- 唯一警告为已有 Starlette/httpx TestClient 弃用提示。

针对性测试命令为：

```powershell
# 在 core.autocrlf=false 的归档目录中运行；测试临时文件位于仓库外。
python -m pytest tests/test_image_followup.py tests/test_backend_evidence_flow.py tests/test_places_discovery.py tests/test_attachments.py tests/test_web_evidence.py tests/test_jev_plugin.py tests/test_jev_shadow.py tests/test_agent_loop.py tests/test_web.py tests/test_map_ux.py -q -p no:cacheprovider
```

覆盖误定位、单一模糊候选不自动选路、来源不升权、模型追加证据冻结、最多两次 Jev 判断、
搜索／正文共享截止时间、免费原始正文回退、私网与重定向拒绝、并发预算、跨会话附件拒绝、
图片任务追问／切换／恢复、日期时分校验、失败类型，以及私有输入在 embedding 预取前过滤。
普通聊天异步预取竞争只允许一个会话写者，另一请求返回 409。

## 发布资产、配置和敏感信息

- 提交差异共扫描 313 个文件，未发现密钥格式、私钥、字面凭据 URL 或直接秘密赋值。
  合成测试值、空模板与占位符按上下文检查；该扫描不是对所有二进制图片的完整人工隐私审查。
- 与基线 `5fd207c` 比较，`data`、Dify 集成与固定评测资料没有版本控制差异。
- 三个新功能开关及 Jev 默认关闭。开启搜索时预算最多每日一美元／一百流程，允许降低，
  未知价格或超额配置拒绝调用／启动；无生产环境变量变更。
- 两个 systemd 单元保留 `ProtectSystem=strict`，新增 `StateDirectory=campuspilot` 和 `0700`，
  为默认 `/var/lib/campuspilot/evidence-budget` 提供可写状态路径。仅验证配置声明，未在生产启动服务。
- 首装脚本 `uv sync --extra api` 从项目依赖安装 Pillow；共享 VPS 依赖脚本明确安装 Pillow。
  旧备份允许列表补齐 MJS、GLB、字体、图片和 webmanifest；没有重烘焙模型。
- whole-package collect 收入 245 个发布文件，包含新增附件／联网模块、桌面模块、GLB、字体、图标。
  107 个二进制网页资产共 7,368,290 字节，单个发布文件最大 1,355,776 字节，小于 25 MB 限制。
- 版本资产哈希 `01e43315d406`，内容发布版本 `r-a747dc5b23c7`。
  GLB、字体、品牌图标、附件 MJS 和桌面 MJS 实际请求均返回 200、字节与发布文件一致，
  且返回 `public, max-age=31536000, immutable`。此检查没有安装或发布该版本。

被测运行时 Git tree 为 `bd09736ea81b9cb24bf0a49d436ab27ba70a6840`，
data tree 为 `830334bbfc86f44cef24388d3955df749a168c2a`，
deploy tree 为 `dd162d1c416a4d59ddbb83a70cba94fdc0360a32`。
本报告随后提交只变文档时，集成方应确认这些 tree 不变；任何核心变更需要重新验收。

## 真实接口与环境限制

固定提交归档中的 `scripts/smoke_places.py` 使用仓库外的私密高德配置独立复跑，只查询三次公开“商学院”。
结果为 `amap:poi:B0FFFCLLP0`，名称“成都理工大学二仙桥校区商学院”，精确命中；
地图搜索、普通聊天与 SSE 地点卡相同，聊天成功并给出导航目的地动作。密钥没有输出或进入仓库。
未重复付费 DeepSeek 测试，也未把地点接口冒烟称为真实步行／现场 GPS 引导验收。

全量结果应按执行环境报告，不能混用：

- 合入前 Windows CRLF 工作区：基线 456 passed / 21 failed，后端 600 passed / 相同 21 failed，
  已登记于 [基线失败清单](qa/backend-baseline-20261014.json)。
- 主集成方报告普通整合 checkout 首轮 599 passed / 22 failed。新增的批准导入校验失败来自换行转换，
  Git blob 与批准哈希相符；本报告在原始字节归档中单独复验该检查通过，不降低校验门槛。
- 主集成方另在原始字节归档执行全量：**618 passed / 3 failed**，Ruff 通过、mypy strict 109 文件通过、
  Node 64 项通过。详情见 [整合记录](qa/integration-20261014.json)，本报告未重复这些全量运行。
  三项仅涉及 Windows 的 POSIX 原子目录链接切换：
  `test_failed_health_check_rolls_back_to_previous_release`、
  `test_legacy_directory_layout_is_migrated_and_used_for_rollback`、
  `test_old_releases_are_pruned_but_current_and_previous_kept`。需在 Linux 独立环境验证；
  十九项换行校验失败在 Git 原始字节下关闭，不是修改语料来绕过校验。

仓库没有 GitHub Actions 工作流；上述是本地检查，不应在 PR 中宣称自动 CI 已通过。
完整联网正文、Tavily 免费真实回退、Jev 独立标注开发／保留集、真机图片与现场路线仍为待验边界。
