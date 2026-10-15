# 官方资料入库维护记录（2026-10-14）

**CONFIRMED：** 用户授权本轮直接采用明确的学校官方公开资料，以及用户保存的通用办事指南，
完成本地 RAG 增量。按 [PRODUCT 的来源政策](../PRODUCT.md#source-authority-and-applicability)
检查发布单位、对象、校区和时间，保留原文证据；无需用户逐条确认。重大且无法自行解决的冲突
保留限制。本轮范围包括保存资料导入、正文和附件解析、条款标注、候选编译、索引及本地发布。
前端和页面样式不属于本轮；没有新增监控、自动刷新或定时任务。线上部署状态仍以
[当前线上基线](../LIVE_BASELINE.zh-CN.md) 为准。

## 文件与处理边界

- `data/cdut/rag/packages/official-20261014/`：公开采集包，`manifest.json` 绑定正文、
  文章 DOM、附件 URL/格式/哈希及日期；`bodies/` 是真实标题加可见正文的派生 UTF-8 文本，
  `raw_dom/` 保留文章子树。已有的八份 `body.html` 按原字节保存；其余子树从已保存 DOM 提取。
- `data/cdut/rag/packages/portal-20261014/`：用户保存的门户通用办事指南。仅沿顶层保存页面
  明确引用的本地 iframe 导入，保留标题、事项代码、指南段落、表格和指南图片；移除个人中心、
  表单值、脚本和导航。`access_scope=authenticated_general` 表示来源访问环境，
  不授权程序登录，也不允许收录个人业务记录。
- [采集审计 JSON](official-collector-probe-20261014.json)：记录原始实验、时间、计数、
  环境摘要和后续离线修复。完整响应、浏览器配置目录、Cookie、登录态和挑战状态不进入采集包。
- `output/official-tools/`：原实验产物与临时视觉核验文件；此前规范化正文备份保存在
  `prior-transcript-backups/`，不冒充新的原始导出。

图片若有明确原始 URL，使用 `attachments`；浏览器只保留了重写后的本地引用时，使用
`capture_assets` 并保留 `source_url=null`。不得从文件名猜造学校附件 URL。未核验的图像文字
使用 `text_verified=false`，不能成为批准条款的证据。PDF/XLSX 先核验实际字节和文件结构，
再解析；HTTP 200 或扩展名本身不能证明附件有效。

## 本轮实际采集结果

初始 headless 实验为 0/18 个正文候选，但其中六次 Drission `TypeError` 属参数错误，
没有完成正文检查。修正参数后 Drission 单独为 0/9，均记录 HTTP 412。
headful 重复实验在三个种子页面、三个轮次、两个工具上得到 18/18 个正文候选；这项计数
仅证明候选检测结果，不证明页面现行有效或条款已采用。Crawl4AI 的最终响应状态未取得，
不能把其初始 412 当成渲染后正文状态。

十个公开目标的原始采集为 8/10 个候选，随后两项实际修复使十篇目标正文都通过提取：

- 研究生自助平台试运行通知的正文位于 `#vsb_content_503`；从现有 DOM 离线恢复，
  保留原选择器漏检结果。
- 本科生电子证明指引是 PDF 承载页。从保存的 iframe 获得准确 PDF URL，使用一次普通
  公开 HTTP 请求取得 284,694 字节的三页 PDF，SHA-256 为
  `b974d6251ecec958cf43d70680adf1031babc88d98e64a54ac4b931cd29fa420`。
  三页均已解析并视觉核验；正文支持申请、下载、核验和注意事项，截图内部文字未全部转录。

本轮后续整理没有重开浏览器。原十篇目标先保留十二个已验证附件，后补获下述砚湖易办手册；
最终采用和发布数量由末尾的执行记录给出，不把候选数当成已入库数量。

## 适用性与附件限制

- 图书馆开馆页面未注明发布日期，`published_on=null`；疫情期间、寒暑假均要求另见通知。
  装饰插画不补充开放时段。
- 2026 年寒假通知是历史假期安排。其 XLSX 的 `Sheet1!A1:E34` 已完整解析；32 个日期
  单元格底层序列对应 2022 年，而标题写 2026 年。中文地区内建 `numFmtId=58` 仅显示月日，
  所以不能断言页面可见内容写了 2022 年，也不能静默修正原值。证据在
  `assets/winter2026/date-format-audit.json`；格式依据为
  [Microsoft OpenXML 文档](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.numberingformat)。
- 砚湖易办 `wxc/.../1241.htm` 是完整的链接索引，其链接的使用手册 PDF 初次下载失败，
  后由一次普通公开 HTTP 请求取得 8,962,969 字节的 18 页原文件，SHA-256 为
  `fb5fc35683cd65d184ce039d6d3c9bd03142c2a049e2e2c3710b1e52d4571c31`。
  `assets/portalmanual/` 归档原文件、全部页文本层及核验摘录；18 页均已视觉检查。
  封面注明网络与信息化处、2022 年 12 月，仅作为月级版本，不设发布日期。
  文本层只有 1,382 字符，多处正文和 UI 为图像；`text_verified=true` 限定已核验文本层与
  选定摘录，`complete_transcription=false`。可支持旧版手册中的服务查找及 PC/移动端
  查看办理进度路径；不保证当前 UI 不变，不将截图中的示例记录当作用户个人业务数据。
  初次失败保留在原实验报告和附件采集历史中。
- 2026-03-26 统一身份认证升级通知限定 3 月 27 日维护时段；不把维护窗口当成当前服务中断。
- 宽带指南保留成都、宜宾校区及各运营商表格；二维码和截图已保存，内部文字未完整转录。
- 成绩复核页面的文字明确“成绩公布 2 周内”。图像只核验并转录了编号标签
  “考试管理 → 查卷申请 → 申请”，图边截断的其他 UI 文字未补全。
  与其他年份规则的潜在期限差异保留适用性限制，不自动推断旧文被废止。
- 第四版学生指南的完整 PDF 为 3,581,743 字节、41 页，SHA-256 为
  `825729937cfd2791c768c2682d1bc1ac41b57a4a6ded57033b0de63f419239b9`。
  全部页的文本层已解析；图片较多，文本层提取不等于所有截图文字完整可检索。
  round5 的独立发布页保存了真实标题、2024-08-31 发布日期及 `saved from url`：
  `https://wxc.cdut.edu.cn/info/1006/3705.htm`。文章内 `showVsbpdfIframe` 明确指向
  `/__local/8/1C/3C/0F34CEA8E563BE8802193833FE4_CFB792C4_36A72F.pdf`，
  与已保留原文件相对应，可离线绑定为独立指南来源。保存页 SHA-256 为
  `2aec7662872b58b209746a67510d5afb196fdf7f8e2737ff74a2d9b914fe3712`。
  月级封面版本“2024 年 8 月”与页面发布日期分别保存。

## 当前维护命令

从仓库根目录运行，使用现有 `.venv`；PDF 解析需要维护依赖 `pypdf`。以下是命令模板，
变量应填写实际路径。提取、附件解析和编译输出必须是新路径，采集包和标注文件分别保存。
保存资料导入不会打开浏览器或读取浏览器配置目录。

```powershell
.venv/Scripts/python.exe scripts/import_browser_exports.py --source $sourceDir --output $newPortalPackage --collected-on 2026-10-14 --map $mappingFile
.venv/Scripts/python.exe scripts/official_knowledge.py parse-attachment --file $attachmentFile --format pdf --output $newAttachmentText
.venv/Scripts/python.exe scripts/official_knowledge.py extract --package $capturePackage --output $newExtraction
.venv/Scripts/python.exe scripts/official_knowledge.py compile --package $capturePackage --annotations $annotations --base $baseCandidate --output $newCandidate --check-only
.venv/Scripts/python.exe scripts/official_knowledge.py compile --package $capturePackage --annotations $annotations --base $baseCandidate --output $newCandidate
.venv/Scripts/python.exe scripts/knowledge_release.py embed --candidate $newCandidate
.venv/Scripts/python.exe scripts/knowledge_release.py preview --candidate $newCandidate --store $ragStore
.venv/Scripts/python.exe scripts/knowledge_release.py publish --candidate $newCandidate --store $ragStore --expected-current $expectedCurrent
```

`--map` 可省略；XLSX 解析使用 `--format xlsx`。`extract` 只产生精确文本候选，
`parse-attachment` 只产生待核验文本。维护者按实际原文完成条款标注：正文/附件的精确引用与
位置、对象、校区、条件、例外和有效时间必须有来源支撑，未知值保持未知。
`compile --check-only` 不写候选，`compile` 不切换当前知识；内容不变时不写新候选。

`embed` 使用配置的 Cloudflare 嵌入服务，凭据读取现有环境或私有配置，不写入记录。
`preview` 核对增删改，`publish` 核验候选及当前版本后原子更新本地 `$ragStore/current.json`，
保留 `versions/` 与 `last_good.json`。`$expectedCurrent` 使用刚核对的版本，首次使用 `none`；
版本漂移则重新预览。发布拒绝仍有 pending 条款的候选。本地知识发布不改变线上部署。
回滚使用已存在的不可变版本，并同样检查当前版本：

```powershell
.venv/Scripts/python.exe scripts/knowledge_release.py rollback --store $ragStore --version $rollbackVersion --expected-current $expectedCurrent
```

`scripts/package_official_captures.py` 只整理已保存的公开产物，依赖原实验隔离环境中的
BeautifulSoup；`--report-only` 只更新审计 JSON。默认命令会重新生成它负责的十篇正文，
重新整理必须显式传入尚不存在的 `--output` 目录，禁止覆盖当前已经标注的采集包。
本次正文和引用附件校验通过；此脚本 Ruff 检查通过。

## 本地编译、索引与发布执行记录

本地当前版本为 `kb-229ee34eba99ef34`，基线为 `kb-f08fa4fd8b583700`。
采用 20 份文档的 44 条核对条款：更新 9 个稳定片段 ID，新增 35 个片段，保留另外
278 个旧片段；最终 176 个来源、322 个片段。候选保存在
`data/cdut/rag/approved-20261014`，当前指针为 `data/cdut/rag/current.json`。

砚湖三篇必需指南均保留完整正文、表格和相关图片，核对后进入知识包。图片原始地址不可恢复
时保留 `source_url:null`，不构造地址。1403 科技立项、1405 团委用印因所引用流程图为空文件
而拒绝采纳；其他合格文档继续构建。额外保留的第四版学生指南未作为完整文字文档入库。

网信处通知栏目首页和实际下一页、教务处考核与成绩栏目共三页取得 28 个去重详情链接；
4 个未读取分页地址保留为待采集项，未声称覆盖全部历史。重跑离线发现结果一致。
三页原始链接证据、发现清单及采集报告均按哈希归档到候选 raw 目录的完整性清单。
另有用户保存的四份公开目录发现 82 个详情链接，独立留档，没有把标题当正文入库。

真实索引采用现有 `@cf/baai/bge-m3`、1024 维：44 个变动片段调用服务生成向量，
278 个文本完全一致的片段复用已校验基线向量，322 行均通过元数据、哈希、有限值及覆盖检查。
凭据只在内存读取，未写入采集包或验证记录。

发布后执行了真实回滚和重新发布，最终仍为上述新版本；`last_good.json` 指向基线。
持有旧检索器的请求保持旧知识版本，后续请求切换到新版本。过期发布预期被拒绝，
重复导入两份包未改变最终知识版本或文档历史。并发发布冲突、损坏候选/索引、嵌入中断、
冷启动/热加载回退由合成契约测试覆盖；失败不会覆写当前成功版本。

七个真实混合检索查询全部命中对应新条款，未降级：报修、账号激活、生源地贷款、
研究生证明次数、校外缴费渠道、本科毕业年级数据边界、成绩复核期限差异。
知识版本、条款 ID、原文位置/哈希、对象、学年和日期字段由检索工具返回。
寒假首末日及相邻日、学年不匹配、研究生专用证明、未知对象不扩大适用均已验证。
详见 [发布及检索记录](official-release-validation-20261014.json) 和
[索引记录](official-index-build-20261014.json)。

独立工具另对三篇砚湖指南执行两轮、每轮每工具独立启动，共 12 次无界面测试。
均收到 HTTP 200 和匹配标题，但正文/事项字段不足，完整正文成功数为 0/12。
没有发现挑战或登录提示，原因仍未确定；不能认定自动工具已稳定获取砚湖指南。
首版使用用户保存的完整浏览器正文；详见
[砚湖独立实验记录](portal-collector-probe-20261014.json)。所有本轮创建的浏览器会话均已关闭。

前端、旧通知列表、结构化事务和办理清单保持现状，本轮发布只更新本地 RAG 快照和检索索引。
没有提交、推送或线上部署。完整回归的最终计数见以下验证记录。

在当前已发布的本地版本下执行 `python -X utf8 -B -m pytest -q`：**743 项通过、3 项失败**。
三项失败均位于既有 `tests/test_release.py`，部署脚本采用 POSIX 原子符号链接替换，
在当前 Windows 系统发生 `WinError 5`；不涉及本轮 JSON 指针知识发布。
本轮相关测试全部通过；所改生产代码、维护命令和测试的 Ruff、严格 mypy 检查通过。
既有批准资料和评估集恢复并保持与 HEAD 完全一致的原始字节；新增 `-text` 属性避免
Windows 检出时换行转换破坏哈希。运行测试的 TMP/TEMP 指向仓库外，避免临时夹具干扰密钥检查。
