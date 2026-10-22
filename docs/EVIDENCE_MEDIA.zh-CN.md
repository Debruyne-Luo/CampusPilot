# 后端地点、联网与图片交接

状态：**CONFIRMED**（方案批准）；后端实现已保存为 `3c0c395`，仍未合入 main 或部署。
前后端统一版本与 GitHub 整合状态见 [整合交接](INTEGRATION.zh-CN.md)。下文测试与本机路径保留原检查截面。
基线为 `5fd207c`，线上仍以 [上线基线](LIVE_BASELINE.zh-CN.md) 为准。

2026-10-15 本地修正：联网查询带学校名称与官方域范围；补证失败或未获采纳时继续回答已收录资料
可证实的部分，并保留联网状态与未知项。显式要求联网不被无本地依据的提前澄清吞掉。
不放宽新网页的官方来源/搜索后判断要求，不改变十秒期限、预算、SSRF 校验或线上开关。
实现与真实回归见 [修正记录](../evaluation/reports/jev-practical-20261014.md)；网页正文可读性仍是限制。

2026-10-15 正文获取修正：直接读取和供应商提取均拒绝防护页、密码登录表单与损坏编码；
HTTP 412 明确返回 `page_protection_required`，不把 HTTP 200 本身视为正文有效的证明。
按 HTTP charset、BOM 或 HTML meta 解码中文，未知编码明确失败。官方来源优先的同时保留
搜索结果的相关性顺序；慢页面耗尽十秒期限时保留已读到的有效正文。原生搜索的独立错误块
不丢弃已返回的有效来源，缓存输入 token 纳入保守费用。公共响应字段与线上开关不变。
十条新题的正文获取实测仍未得到可用官方正文，详情见
[正文验证记录](../evaluation/reports/web-body-validation-20261015.md)；不能据此判断 Jev 的联网质量。

2026-10-15 回答体验与固定证据对照：简单问题直接回答，操作问题给必要步骤；只有会改变答案的
用户条件缺失才追问，资料缺失不再转成身份追问。保留已有依据的部分回答，生成服务故障与证据
不足分别说明，公共 API 不变。Tavily 凭据已在仓库外配置，用户确认免费方案且未启用按量付费；
两道先导题仍未取得相关业务正文，故未扩到十题。主回答模型在本机与 VPS 的生成诊断均超时，
最终回答的 Jev 开关对照仍为 **OPEN**。本轮实现、证据判断与质量验证的区别见
[回答体验验证记录](../evaluation/reports/answer-experience-20261015.md)。线上开关与部署未改变。

## 行为与接口

- `POST /api/places/search`：浏览器会话、Origin 和自定义头保护，输入 `query` 与可选 `category`。
  返回 `places`、`sources`、`provider_status`、`resolution`、`map_pick_available`；明确区分目录命中、
  高德命中、无结果、超时、未配置、配额和服务故障。地图是否加载不影响后端检索。
- 地点目录与高德使用同一查询服务。本地 ID 保持 `cdut:`，临时高德 POI 保持 `amap:poi:`，
  仅支持找路。精确匹配优先，未知教室代码要求确认；单个模糊候选也不自动选为路线目的地。
- `POST /api/attachments`：原始二进制图片，`Content-Type` 指定格式，`X-Attachment-Name` 为编码文件名。
  返回 `attachment_id/name/mime_type/size`。每次一图、最多十 MiB，三图分别上传。
  `GET/DELETE /api/attachments/{id}` 按会话隔离；浏览器同源 GET 支持无 Origin，但必须有自定义头和同源 Fetch Metadata。
- `/api/chat` 与 `/api/chat/stream` 接受 `{message, attachment_ids}`，最多三个 ID；有图片时允许空文字。
  后续省略附件可沿用当前图片，新附件替换当前组。删除、过期和重置会清理引用。
- 图片先校验实际格式、方向与像素上限，再去元数据、缩到最长边 2048、每图至多两 MiB模型载荷。
  默认每会话最多二十四张、三十二 MiB，全应用二百五十六 MiB；每分钟回收失效附件。
- 阅读课表、通知原文走图片阅读路径，标明“用户上传、未经学校核验”；核实政策走目录、RAG与联网。
  Jev 完成判断后冻结该轮证据，不允许模型继续追加未经判断的工具材料。
- 图片任务与附件引用分开记录；先提出读图任务再上传、纯图延续该任务和短追问均可继续。
  无关的新问题不把旧图发送给理解或回答模型；用户仍能用“这张图”恢复阅读。
- 网页补齐选择、粘贴、预览、删除、上传进度和重试。新对话使用后端 reset，保留独立办理清单。

## 配置与费用

三个开关默认关闭，便于独立启用和回退：

```dotenv
CAMPUSPILOT_RUNTIME_MODE=phase2
CAMPUSPILOT_AGENT_LOOP=on
CAMPUSPILOT_AMAP_DISCOVERY=on
AMAP_WEB_SERVICE_KEY=  # 单独的 Web 服务 Key；不能直接复用 JS Key
CAMPUSPILOT_IMAGES=on
CAMPUSPILOT_WEB_SEARCH=on
CAMPUSPILOT_WEB_SEARCH_PROVIDER=deepseek
CAMPUSPILOT_EVIDENCE_BUDGET_DIR=/var/lib/campuspilot/evidence-budget
CAMPUSPILOT_EVIDENCE_DAILY_USD=1
CAMPUSPILOT_EVIDENCE_DAILY_FLOWS=100
CAMPUSPILOT_JEV=on
CAMPUSPILOT_JEV_MODEL=typesafe/jev-1.13
CAMPUSPILOT_JEV_KEY_FILE=/PRIVATE/PATH/openrouter-jev-key.txt
CAMPUSPILOT_JEV_INPUT_USD_PER_MILLION=0.042
CAMPUSPILOT_JEV_OUTPUT_USD_PER_MILLION=0
TAVILY_API_KEY=
TAVILY_FREE_PLAN_CONFIRMED=false
```

2026-10-21 改为 DeepSeek 独立 `POST /v1/tools/search`、`POST /v1/tools/fetch`，
不再以模型消息工具模拟搜索。Search 请求 `need_content=true`；已有完整正文不重复 Fetch。
按[官方独立工具说明](https://api-docs.deepseek.com/guides/search)保守预留每次 $0.00075，
成功非空按该额结算，明确失败或空结果按零结算；超时、取消、未知响应保留预留。
旧 `SEARCH_INPUT/OUTPUT_USD_PER_M` 配置继续接受以兼容旧运行环境，但不用于独立 Search/Fetch 计费。
Jev 价格配置仍按 [OpenRouter](https://openrouter.ai/typesafe/jev-1.13) 核对。
并发共用账本，达上限就降级；后续部署需再次核对价格。
配置可降低额度；超过每天一美元或一百次流程会拒绝启动，不能靠环境变量扩大批准预算。

Tavily 必须确认免费账户、无自动付费后才将 `TAVILY_FREE_PLAN_CONFIRMED=true`，并保守限制每月一千次基础查询。
原生正文被学校访问保护阻止时，可在剩余截止时间和读取额度内使用供应商 `raw_content`，
标为 `provider_extraction`；摘要或生成答案不作正文。缺备用凭据时返回明确限制。

本轮共享十秒截止时间、最多两次 Search 和三页正文；不截断正文后把它称作完整政策。
搜索列表、登录或访问验证页不能进入答案；不同校区材料分开核对。
真实 Search/Fetch 与交互检查见 [2026-10-21 报告](qa/student-experience-20261021.md)。

## 验证与待验边界

以下为 2026-10-14 最终代码检查与供应商实测。真实模型测试使用纯合成图片和公开查询，
密钥始终在仓库外，不输出或写入此记录。

- 全量 Python：**600 passed / 21 failed**；原始 `5fd207c` 工作区同环境对照为 **456 passed / 同21 failed**。
  新增与修改的契约检查未引入新失败。Node **56 passed**，Ruff 全项目通过，mypy strict **109 files** 通过。
  最终全量详情保存于 JUnit（本机归档 `output/evidence-media/final-pytest.xml`）。已知失败分类如下，未改历史数据来绕过校验：

  | 分类 | 失败数 | 原因 |
  | --- | ---: | --- |
  | API 评测与迁移门禁 | 16 | 固定样题文件与已登记哈希不符 |
  | 历史知识包与微信导入 | 2 | 提交的历史包版本／校验和不符 |
  | 发布切换 | 3 | Windows 拒绝 POSIX 目录链接原子替换 |

  完整失败列表见 已知基线失败（本机归档 `output/evidence-media/known-baseline-failures.json`）。
  此前工作区未提交时，用 代码与测试指纹（本机归档 `output/evidence-media/review-manifest.json`） 绑定检查截面：
  `92cef43fa911ecbef9e08972d9d05f4a827cedfbfbf04e70da94c1575f6050cf`。
  指纹覆盖基线提交及 331 个非文档文件，不替代未来 Muse 所需的 Tested Commit SHA。

- DeepSeek 真实图片识别通过（合成标记 BLUE-731）；最后单独调用 **1.306 秒**、完整 Agent 阅读 **3.175 秒**，
  图片追问 **3.343 秒**，随后切换 E2A403 校园任务通过。阅读路径为 `agent_image/success`，官方引用为零。
  冒烟共享账本累计保守占用 **USD 0.306964392 / 14 调用 / 3 联网流程**，含未知用量保留的最大费用，
  不等同于供应商实际账单；早期独立图片调用未记入该账本，不能宣称完整费用审计。
- DeepSeek 原生搜索成功返回真实结构化学校来源；本机 VPN 假 IP 被拒，VPS 对三条学校页面返回 HTTP 412。
  这些页面正文未取得，不能宣称完整联网问答通过。免费备用尚缺配置，未将摘要当作官方证据。
- Jev 真实接口可调用；本次样题返回 `unsure`，不会用于放行答案。需要独立标注开发／保留集校准。
- 用户补充高德 Web 服务 Key 后，真实“商学院”查询通过：返回
  `amap:poi:B0FFFCLLP0`、名称“成都理工大学二仙桥校区商学院”、GCJ02 位置
  `104.146544,30.677529`。地图搜索、普通聊天与 SSE 返回相同单一精确地点，聊天保留高德来源和导航动作。
  实测发现并修复“二仙桥校区”限定前缀的名称归一化；学生工作办公室后缀不升级为学院本身。
  浏览器点击“带我去”、选择目录中的东区图书馆为起点，真实高德 Walking 返回约 **541 米、7 分钟**；
  目的地使用供应商坐标，GPS 请求为零，聊天 payload 不含坐标。截图和限制见 [前端交接](EVIDENCE_MEDIA_FRONTEND_HANDOFF.zh-CN.md)。
  这是浏览器路线规划，尚不能据此宣称真机或现场入口、GPS 前台引导通过。
- 浏览器本地合成服务验证上传、规范化预览、纯图片发送、E2A403 单一地点卡、新对话清理；
  手机尺寸 390×844 已检查，未把此测试称为真机路线验收。
- 旧基线已有固定题哈希、历史知识包和 Windows POSIX 发布切换测试失败；本轮逐项记录，
  不改旧知识包或降低门槛来使历史测试通过。

独立交叉检查发现的未知教室宽泛匹配、外观猜测定位、模糊候选自动路线、额外检索绕过Jev、
图片金额升权、小额费用及楼层校验遗漏均已补修复与回归。
最后补齐图片短追问与新话题隔离、截止日期／时钟等价及歧义拒绝、格式和事实校验失败分类、
embedding 预取后的会话忙态复检，以及私有文本在普通／流式预取前拒绝。
[独立复查报告](EVIDENCE_MEDIA_QA.zh-CN.md) 明确实现者自身回归与跨模块只读 QA 的不同范围。

保留集通过率目标 95% 与无依据关键事实为零**尚未进行独立校准与保留集实测**；
不能以本轮自动测试的通过数量替代该产品验收。错误选点和错误联网率也未形成代表真实用户分布的统计。
后续先用独立标注开发集固定 Jev 门槛，再一次性运行保留集，记录任务通过率、关键事实、
错误选点、错误联网率、p50/p95 时延、失败原因及共享费用账本，不根据保留集结果继续调门槛。

## 交付与启用

新增依赖 Pillow，`uv sync --locked --extra api --extra vector` 即可安装。
运行已有 pytest、Ruff、mypy strict 和 Node 检查；真实冒烟入口为 `scripts/smoke_evidence_media.py`。
`--skip-search --agent --followup` 可验证真实图片、续问及任务切换而不重置已有搜索账本。
`scripts/smoke_places.py --amap-env <仓库外配置绝对路径>` 验证高德、普通聊天与流式契约一致性，
只读进程内密钥，不把高德 Web 服务 Key 下发浏览器。
本地合成界面入口为 `scripts/preview_evidence_media.py`，不使用真实学生图片或产生外部推理。

桌面改版工作区保持原样，重叠文件的兼容合入步骤见
[前端交接](EVIDENCE_MEDIA_FRONTEND_HANDOFF.zh-CN.md)。发布时同时使用更新的 Caddy 附件路径大小限制；
只打开后端开关而未更新代理会导致图片请求被旧的十六 KiB上限拒绝。
缺凭据、独立 QA 或保留集验收不能宣称产品验收完成；最终部署和合并由用户决定。
