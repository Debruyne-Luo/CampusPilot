# CampusPilot → DeepSeek Harness 交接

记录日期：2026-10-09（北京时间）。用户指定由 DeepSeek Harness 接手后续完善。
本文件是本地交接材料；尚未启动 Harness，也没有向外部工具发送项目或凭据。

## 打开哪个项目

实际工程工作区：`D:\Projects\CampusPilot`。从这个目录开始工作。
最新网页、后端、数据和部署成果包含大量未提交/未跟踪文件，尚未提交或推送；
直接打开当前本地工作区才能取得完整版本。保留全部已有成果。

线上地址：https://campuspilot.38-244-61-184.sslip.io 。访客入口有访问口令。
本机上一轮临时测试服务器和浏览器已关闭，生产服务保持运行。

先读 [AGENTS](../AGENTS.md)、[产品范围](PRODUCT.md)、[架构](ARCHITECTURE.md)、
[最新交付状态](SUBMISSION_STATUS.zh-CN.md) 和 [接口契约](API_CONTRACT.md)。
部分旧文档保留阶段历史，以最新增量及接受的ADR为准；当前已接入真实高德和Dify工具回调。

## 模块交接记录

| 项目 | 当前记录 |
| --- | --- |
| 模块名称 / 目标 | CampusPilot 提交版；在已上线版本上继续完善校园查询、办事与地图行动流程 |
| 当前状态 | 双模式、官方资料查询、站内路线和前台步行引导已实现、开发验收并发布；真实校园步行/iOS仍待验证 |
| 上游输入 | 用户需求；公开官方资料；本地业务目录；高德GCJ02地点/路线；仅主动开启时的浏览器定位 |
| 下游输出 | 短答、官方依据、业务ID卡片、步骤/入口、地点与参考路线；缺位置时保留文字 |
| 接口 / schemas | API_CONTRACT；地图消息含请求编号和iframe代号；个人坐标不进入/api/chat或Dify |
| 依赖 | Python3.14.7、FastAPI、原生HTML/CSS/JS、高德JS API、Dify Cloud、现有轻量VPS；保留单主Agent/模块化单体 |
| 允许修改范围 | 按用户后续任务修改相关代码、正式数据、测试和文档；延续既有备份发布流程 |
| 禁止修改范围 | 丢弃已有工作、伪造校园事实/坐标/路线、擅自换框架或供应商、擅自Git提交/推送/合并、修改无关服务 |
| 数据来源 | 明确官方文件可直接采用并记录来源、日期、对象及限制；实质矛盾或非常不确定时才交用户复核；合成数据仅用于测试 |
| 已知问题 | 精确网安楼/补卡设备坐标未补齐；校园真机GPS、iOS、校园网与独立QA待完成；公众号尚无真实文章导入或自动采集 |
| 风险等级 | 本地文档/UI变更可回退；部署影响线上需沿用备份、哈希与失败恢复；后台/室内导航及个人学校账户操作仍在原边界外 |
| 测试 | 2026-10-08：188项pytest、6项JS进度测试、Ruff、相关mypy及6组本地浏览器检查通过；生产真实地点/路线与两类Dify业务查询通过 |
| Tested Commit SHA | 本增量未提交，未由Muse锁定独立验收SHA；不把工作快照或开发自测冒充独立QA |
| QA结果 | 开发检查PASS；真机、校园步行和独立QA尚未执行；完整证据/既有类型检查问题见SUBMISSION_VALIDATION |
| 验收标准 | 修改目标的真实交互与失败降级可用，桌面/手机可操作，不重发对话、不串台；源数据可追溯，测试与实际验证记录一致 |
| 相关ADR / 文档 | ADR0004；SUBMISSION_STATUS、SUBMISSION_VALIDATION、SUBMISSION_DEPLOY、WEB_GUIDANCE、KNOWLEDGE |
| 负责人 / 评审人 | 用户指定DeepSeek Harness接手；用户保留最终产品决策与Review/Merge |
| QA负责人 | 原约定Muse独立QA职责保留；本次实际独立执行安排为OPEN |

## 代码入口

| 路径 | 用途 |
| --- | --- |
| `backend/src/campuspilot/web.py` | 网页、匿名会话、聊天、资料与高德固定上游代理 |
| `backend/src/campuspilot/api.py`、`directory/`、`presentation.py` | Bearer工具接口、确定性业务查询、ID关联卡片 |
| `backend/src/campuspilot/dify.py` | Dify适配；开发用Harness模型与线上Dify模型互不自动切换 |
| `backend/src/campuspilot/knowledge.py`、`data/cdut/knowledge.json` | 6条官方资料的本地确定性检索、日期/对象过滤 |
| `backend/src/campuspilot/web_assets/` | 原生前端；app双模式，journey查询/路线，map-frame地图，map-discovery动态地点，guidance前台引导 |
| `data/cdut/` | 4项事务、20条目录地点、5位教师及来源；14个高德建筑坐标候选保持原核验状态 |
| `integrations/dify/` | 已导出DSL与语料；原经济型关键词RAG保留，线上两个LLM仍为dsv4 |
| `deploy/`、`scripts/`、`tests/` | 固定文件备份发布、资料导入/导出、工作快照打包及回归 |

不要将本地资料检索描述为已经建成新的向量RAG；当前没有自动公众号爬虫/OCR。
高德热点、2公里周边搜索和地图选点扩展目录，不能宣称全校每个房间/设备都已准确收录。
前台引导会在切助手、离开前台或锁屏时暂停；详见 [WEB_GUIDANCE](WEB_GUIDANCE.zh-CN.md)。

## 下一步建议（PROPOSED）

1. 优先用校园真机验证前台GPS、精度、偏航、到达与暂停/恢复，检查iOS Safari和软键盘；
   没有真机证据时保留待验状态，不用合成定位代替。
2. 按官方来源补充办事信息、教师房号和确切设备/建筑点位；遇到缺字段先保留文字降级。
3. 沿 [知识接入流程](KNOWLEDGE.zh-CN.md) 接入可确认发布单位的公众号文章，保留日期、
   对象、原文与修订关系；不能把所有公众号都能自动抓取当作现有能力。
4. 按 [比赛展示方案](DEMO_STRATEGY.zh-CN.md) 做可复现演示与同学试用；先收集实测数据，
   再宣称节省时间或任务成功率。目标用户建议为新生与偶尔办事的学生。

具体下一项以用户给Harness的指令为准，这份建议不自动批准新架构或敏感业务写操作。

## 复现与部署

在根目录运行已有环境，无需重建工程：

```powershell
Set-Location D:\Projects\CampusPilot
.venv/Scripts/python.exe -m pytest -q
node --test tests/guidance_progress.test.js
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
.venv/Scripts/mypy.exe backend/src tests/test_routes.py tests/test_knowledge.py tests/test_route_update.py
```

完整验证范围与浏览器步骤见 [验证记录](SUBMISSION_VALIDATION.zh-CN.md)。全库mypy尚有
两个既有测试文件的29项标注问题；上面的命令是实际通过的相关检查范围。
本地无云端凭据预览可用 `uv run --locked --extra api python -m campuspilot.web`；真实地图、
聊天配置与部署读取 [部署记录](SUBMISSION_DEPLOY.zh-CN.md)。
私有配置在仓库外 `D:\Projects\.campuspilot-private`，只供必要的启动/部署使用，
不得把值输出到日志、交接文本、模型提示词或源码包。

用户此前已授权按既有流程备份并同步后端/静态资源、失败恢复；Git提交/推送/合并未获授权。
专用SSH别名 `campuspilot-vps` 已可用，保留严格主机指纹和现有服务。
不要直接拿早期静态更新器覆盖新功能；按改动选用固定文件发布器并验证回滚范围。

上一轮完整源码快照：`release-backups/campuspilot-20261008T155354Z.zip`，
SHA256：`b9ee276feff45fab8030832782062023929c5115a6a8311377562de0e44f9ef0`。
该包是未提交工作快照，包含已发布运行文件；本交接文档是在该快照后新增。
后续更新可将该包作为对应运行文件的旧哈希基线，先确认服务器没有漂移。

最新运行增量备份：`/opt/campuspilot/workspace-backups/20261008T154314Z-5d1f1042`。
发布检查必须按实际JS SDK协议带 `s=rsv3` 等参数；已验证裸Web Service请求会得到
`USERKEY_PLAT_NOMATCH`。最新发布器已修复这一点，失败会恢复旧文件并检查健康。
