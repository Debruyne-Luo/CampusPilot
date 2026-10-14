# 地点、联网和图片：QA 交接

日期：2026-10-14。对象为 `feat/backend-evidence-media` 的**未提交工作区**，
Git HEAD 基线 `5fd207cdd557f34aae6dc6d9736815749a206308`；不是该提交本身的测试结论，
也不是部署、合并或产品验收许可。后续修改须重跑相关检查。

## 结论与独立性

当前后端整合范围 **PASS，审查发现已修复且复验关闭，无已知阻塞问题**。
真实供应商、浏览器和保留集验收边界见下文；PASS 不能替代这些尚未完成的产品验收。
审查者承担过 `web_evidence`、Jev 和预算模块的实现，因此这些模块的测试只能称为开发回归；
对主集成方修改的 Agent、配置、附件与地点整合实施了独立只读审查和对抗复现，未为通过测试改核心代码。

最终图片任务与失败类型截面，八个文件 **209 项通过**；最后的私有输入预取修复后，
又复验 `test_backend_evidence_flow.py` **36 项通过**（原 34 项及新增两个入口），
另独立复现普通与 SSE 入口均没有发起 embedding 或模型调用。
当前 focused 集合合计覆盖 **211 项**；这个总数是覆盖统计，没有声称最后一步重新执行了全套 211 项。

- `test_backend_evidence_flow.py`、`test_places_discovery.py`：36 与 13 项，覆盖主集成、预算上限与地点边界。
- `test_attachments.py`：17 项，覆盖另一实现者的附件、会话及传输边界。
- `test_image_followup.py`：48 项，覆盖 typed 图片任务、续问、话题切换、日期及时分等价。
- `test_agent_loop.py`：39 项，覆盖既有 Agent 与新增失败类型兼容。
- `test_web_evidence.py`、`test_jev_plugin.py`、`test_jev_shadow.py`：58 项，开发回归，不声称独立 QA。

运行使用 Python 3.14.7 的实际解释器和现有项目依赖。可复现命令：

```powershell
$env:PYTHONPATH = 'D:/Projects/CampusPilot-backend-evidence-media/backend/src;D:/Projects/CampusPilot/.venv/Lib/site-packages'
& 'C:/Users/21207/AppData/Roaming/uv/python/cpython-3.14.7-windows-x86_64-none/python.exe' -m pytest tests/test_image_followup.py tests/test_backend_evidence_flow.py tests/test_places_discovery.py tests/test_attachments.py tests/test_web_evidence.py tests/test_jev_plugin.py tests/test_jev_shadow.py tests/test_agent_loop.py -q --basetemp C:/Users/21207/AppData/Local/Temp/campuspilot-final-qa5 -p no:cacheprovider
# 最后改动的单独复验：
& 'C:/Users/21207/AppData/Roaming/uv/python/cpython-3.14.7-windows-x86_64-none/python.exe' -m pytest tests/test_backend_evidence_flow.py -q --basetemp C:/Users/21207/AppData/Local/Temp/campuspilot-final-privateQA -p no:cacheprovider
```

临时目录应在仓库外：旧凭据测试明确要求临时测试密钥在仓库外；仓库内 basetemp 会触发正确的拒绝。
本机 venv 启动器存在临时目录写权限异常，实际同版本解释器运行成功，没有更改 Python 版本。
唯一警告为已有 Starlette/httpx TestClient 弃用提示。

## 已复验的对抗缺陷与安全边界

主集成方修复以下审查发现，回归及独立复现已确认：

- 未知 `E9Z403`、`E2D403` 不再被“东教”别名覆盖；没有错误楼栋或自动路线。
- 外观猜测不能作为图片中的可见文字建立目的地；无真实图片时虚构图片字段也不再为地点背书。
- 单个模糊高德候选须选择，不自动生成 `plan_route`；真实精确命中与用户确认才允许确定目的地。
- Jev 路由完成后冻结证据，模型追加工具请求不能引入未经判断的校园事实。
- 图片中的金额不进入官方事实验证材料；仅阅读用户图片采用单独归属并标明未经学校核验。
- 无依据的小额收费、楼层和入口被校验拦截；用户教室编号复述不放行其同时提供的电话或金额。
- 官方 DeepSeek `/v1` 问答地址仍可复用搜索密钥。
- 新功能配置可以降低每日预算，超过一美元或一百个联网流程会拒绝启动；旧独立 Jev 配置保持兼容。

新增图片任务审查发现已修复并独立复验：

- 原文 `2026-10-14 17:00` 不能再被答为 `10月15日` 或 `2026年10月14日18:00`。
  同值完整日期、省年月份日期和明确时分格式可等价，变更月日／时分及无效日期拒绝；
  “中午非十二点”和“晚上十二点”的跨十二小时／跨日歧义保守拒绝，不错误归一成凌晨或正午。
- `ImageTask("读这张通知，要求交什么")` 后，`什么时候商学院关门`、`帮我解释学校食堂收费标准`
  不再因前缀被当作图片追问。短省略主题续问使用完整匹配，新校园任务剥离旧图，显式提图可恢复。
- 读图的数字依据仅限可见文字；描述性观察中的猜测金额／日期不能扩权。
- 普通聊天在异步预取后再次检查 busy；独立屏障回归确认同会话仅一请求成功，另一请求 409，模型只调用一次。
- 私有输入在 ordinary／SSE 的 embedding 预取前过滤，避免最终拒绝答复之前已将原文传给外部模型。
- 对外明确区分 `model_format`、`answer_validation` 和上游超时／额度；图片服务故障不会误要求用户更换高清图片。

其他审查范围：

- 三个功能开关默认关闭；搜索价格未知时不启动付费调用。搜索和在线 Jev 共用美元账本，
  搜索流程单独计数；并发预留、失败保留最大费用及月度免费查询额度有回归。
- 附件上传／删除与聊天采用 Origin、自定义头、会话保护；读取的无 Origin 例外限同源 GET。
  跨会话访问返回 404；超限、格式伪装、多帧、元数据清除、过期、重置与断流释放均已验证。
- 本地网页读取验证全部 DNS 结果并固定公网地址，保留 Host/TLS SNI；每次重定向重新检查，
  私网、元数据地址、混合 DNS、转译地址、超大响应拒绝；合法锚点先去掉再取正文。
- 原生搜索仅接受结构化搜索块；正文不可读时，在同一个 10 秒截止时间内尝试免费备用。
  最多两次搜索和三页读取，Tavily 只接受原始 `raw_content`，保留 `provider_extraction` 归属，
  不把 `content`、摘要或生成答案当正文。在线 Jev 每轮最多两次实际判断。
- 高德候选保持临时 `amap:poi:` 与 `location_only`，不升级目录核验或办理地点关联；范围、名称、
  有限 GCJ02 坐标、重复结果及配额冷却均有回归。个人实时位置没有传入聊天或 Jev。

## 真实验证与待验边界

- 已独立使用真实高德 Web 服务 Key 复跑 `scripts/smoke_places.py --amap-env`：仅三次“商学院”
  公开查询，密钥在仓库外由脚本读取且未输出。返回 `amap:poi:B0FFFCLLP0`，名称“成都理工大学二仙桥校区商学院”；
  地图搜索接口、普通聊天和 SSE 的地点卡一致，均精确命中，聊天成功返回导航目的地动作。
  独立名称断言确认成都／二仙桥校区前缀可归一，宜宾校区及“办公楼”业务后缀保留。
  本测试关闭了真实“商学院”地点查询覆盖缺项；主集成方另报告真实浏览器规划步行路线成功，
  约 541 米／7 分钟且 GPS 调用计数为零。后者不是本审查者的独立浏览器结果，也不是手机实地引导验收。
- 主集成方报告 DeepSeek 真实视觉、完整 Agent 首次读图、图片追问及切换到 E2A 的新任务通过；
  最新记录约 1.306／3.175／3.343 秒，样本为合成图片，不替代照片保留集。
  结构化原生搜索成功，但目标学校页面返回 HTTP 412，
  本机 VPN 的私有假 IP 被正确拒绝；不能据此宣称完整联网问答成功。
- Tavily 免费凭据尚缺，真实原始正文回退未经实测；免费账户／关闭自动付费仍须配置方确认。
- Jev 真实样题的 `unsure` 结果不能替代校准；独立标注的开发集与保留集、95% 通过率、
  无依据关键事实为零以及时延、误联网率、费用统计尚未完成。
- 本次是后端 focused QA，不包含完整桌面改版、真机相机／相册、多图真实照片或真机路线验收。
  主集成方的浏览器结果见 [实现交接](EVIDENCE_MEDIA.zh-CN.md)，不提升为真实设备验收。
  其共享账本记录约 USD 0.306964392、14 次调用／3 个搜索流程，包含未知用量的保守预留，
  不能当作供应商实际账单或本审查者重新对账结果。

主集成方已将全量测试中的 **21 项失败**与旧基线对照，涉及固定题哈希、历史知识包及 Windows
POSIX 发布切换测试；本次 focused QA 没有重新执行那组基线比较，不能据此宣称全量测试通过，
也不将其计入本轮新功能回归失败。后续发布交接应附主集成方的完整失败清单和基线对照输出。

主集成方最终全量为 **600 passed / 21 failed**（旧基线 **456 passed / 同21 failed**）、
Node **56 passed**、Ruff 全项目通过、mypy strict **109 files** 通过。
这是主集成方执行证据，不改写上述独立 focused 检查的范围；
[完整结果与源文件指纹](EVIDENCE_MEDIA.zh-CN.md) 可供后续 Muse 复核。
