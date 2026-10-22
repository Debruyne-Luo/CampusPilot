# 最终知识库与 RAG 本地启用（2026-10-21）

当前本地正式版本为 `kb-1d15bf97b31c0d90`：192 来源、402 片段及匹配的 BGE-M3 向量，
与 36 项服务、41 地点共同绑定发行。已通过现有正式门槛并重载启用，旧版本保留回滚。
本地采用 BM25，保留向量/混合能力；54/60 答题通过，时延目标尚未达标。
采纳依据、原件、检索比较、剩余失败及启动/回滚见
[最终交付记录](qa/final-knowledge-20261021.md)。此状态不代表线上部署。

# 知识库实施状态（2026-10-17，历史记录）

本页后续章节保留各阶段的历史决定。最新授权是 [ADR 0007](adr/0007-knowledge-quality-and-recollection.md)：
保留技术主干，向后兼容扩展 v2 证据契约、适用性和服务完整度，并对资料重新核验。
它取代下文“保留既有 schema 不动”的早期限制；旧快照本身仍保持不变。
实现、候选版本、实际采集边界、验证结果及未完成验收见
[当时交付记录](KNOWLEDGE_REBUILD.zh-CN.md)。当时的候选尚未发布；最新实际状态见页首。

# 官方通知与资料增量（2026-10-08）

用户明确授权：可搜索到的明确官方资料直接采用，不要求逐项人工确认；只有高度不确定、
有重大冲突且自行研究无法解决的内容才请求复核。正式规则见 PRODUCT。

## 实现

- `data/cdut/knowledge.json`：6份来源明确的资料，覆盖校庆展览、寒假信息服务、校园网、
  正版软件、图书借阅、研究生证明。官方搜索索引可读但源站返回412的记录如实标记访问方式。
- `knowledge.py`：确定性关键词检索、对象和时间筛选、来源URL校验、替代版本处理。
  当前路径不调用大模型，不宣称新建了向量RAG。Dify既有经济型RAG保持原样。
- 页面顶部“通知与资料”提供查询、类型、人群和时间筛选；卡片展示要求、原文和已关联地点。
- 对话可问“校园网无法上网怎么办”“校庆活动什么时候截止”“本周有哪些活动”。
  查询不到当前活动时只说明已收录资料中无匹配，不推断学校没有活动。
- 日期按北京时间判断；报名截止日按当日结束处理，当前快照只含日级时间，不接收需要
  精确到时分才能正确判断的报名记录。遇到此类通知需先扩展时间契约或保留为原文资料。

## 资料采用与更新

1. 从官方页面、可读官方搜索索引、官方文件或能确认发布单位的公众号文章整理事实。
2. 记录原文URL、发布单位、发布日期、收录日期、适用对象及原文段落；不把文章当作模型指令。
3. 按 `knowledge.json` 的字段准备JSON数组。原文中没写的日期/地点保留null，不外推。
   官方公众号需记录 `source_kind=official_wechat` 和学校官网的发布者身份依据URL。
4. 用以下命令校验并采用，不需要用户逐项批准。脚本校验格式与引用，不冒充联网事实核验。

```powershell
.venv/Scripts/python.exe scripts/import_knowledge.py --input <prepared-records.json> --check-only
.venv/Scripts/python.exe scripts/import_knowledge.py --input <prepared-records.json>
.venv/Scripts/python.exe scripts/export_knowledge.py --output integrations/dify/official-knowledge.md
```

导入原子更新并按内容哈希保留旧快照；重复来源拒绝，旧收录日期拒绝覆盖新快照。
同源修订用原ID更新；新更正文件用新ID和supersedes，不删除历史。启用时载入单一快照，
正式更新沿用备份、发布与重启流程。Dify Markdown导出仅是可用语料，不自动上传云端。

## 目前边界

- 当前没有自动抓取任意公众号、定时同步或OCR；已实现整理后统一导入，公众号适配仅通过
  合成契约测试，尚未收录真实公众号文章。源站访问失败不绕过访问控制。
- 这批搜索结果以旧资料为主；已结束的寒假/校庆安排默认有明确状态，时间筛选排除过期记录。
- 仍没有证据足以把补卡设备绑定为当前可用的具体地图点，也没有补造网安楼坐标。
- 本科电子证明详情仍未取得足够正文，不从研究生规则推断本科流程。
- 无个人位置、学校密码或用户聊天记录进入知识库；网页只按文本渲染原文摘要。

## 验证与交付

开发检查及本轮发布结果见 SUBMISSION_VALIDATION、SUBMISSION_DEPLOY。
本增量沿用既有备份与发布授权；Git提交、推送与合并保持由用户决定。

## 知识库构建方案（2026-10-17 决定）

用户授权：可完全重新收集内容，并自行决定构建方案调整。决定如下。

### 不重做，重写内容

保留既有 schema、快照发布链、回滚机制（`approved-*`、`versions/`、`last_good`）不动；
旧快照转只读基线，不再往旧标准灌新内容，回滚随时可用。

### 五类集合与准入线

物理上仍是单一快照，逻辑上用类别隔离，避免改动检索器读取路径。缺准入线的内容只进
目录层，不进正式库。

| 集合 | 载体 | 准入线（缺一不进正式库） |
| --- | --- | --- |
| 事务 | `services.json` | 有可验证的办理入口或官方指南正文；不编办理步骤 |
| 部门 | `offices.json` | 有官方名称；已知部门不推断地点 |
| 地点 | `places.json` | 名称+类别；无证据不填坐标 |
| 教师 | `teachers.json` | 姓名+部门+官方主页三件套 |
| 通知 | `knowledge.json` | 有发布时间且有明确时效 |
| 政策正文 | `rag/` | 全文或原文段落；纯链接/转述/无出处拒收 |

### 目录发现层（采集与正式库之间的缓冲）

`data/cdut/rag/packages/bsdt-services-20261017/` 是砚湖易办办事大厅的公开目录采集结果，
`authority: candidate_only`，不含采纳。内容：

- `discovery.json`：采集证据与已知边界，含原始返回哈希
- `service_index.json`：135 条目录（编号/名称/部门/服务对象）
- `service_details.json`：135 条办理详情（办理方式/途径/时间/咨询电话/事项性质/办结时限等）
- `service_enriched.json`：从官方 `desc` 解析的费用/办事依据/地点/注意事项
- `services_full.json`：合并后的完整候选

采集只读 `/EIP/nonlogin/` 公开路径，不使用凭据；登录后的办理流程、表单与个人数据不采集。

### 边界：事务知识到"指南级"，不到"步骤级"

办事大厅公开的字段止于办理入口、时间、电话、所需条件与注意事项；完整办理步骤与表单在
统一身份认证之后。因此事务集合当前能回答"找哪个部门、电话、办理时间、要带什么、多久办结"，
不能回答逐步操作流程。补齐步骤级内容需要公开的部门办事指南页，见下条现状。

### 复现命令

```powershell
.venv/Scripts/python.exe scripts/capture_bsdt_services.py --output output/bsdt-capture
.venv/Scripts/python.exe scripts/capture_bsdt_service_details.py --index output/bsdt-capture/service_index.json --output output/bsdt-capture
.venv/Scripts/python.exe scripts/enrich_bsdt_services.py --input output/bsdt-capture/service_index.json --output output/bsdt-capture
.venv/Scripts/python.exe scripts/promote_services.py --input output/bsdt-capture/services_full.json --output output/bsdt-capture --allow-navigation-step
```

### 准入门的实测结论（重要）

用真实 `CampusService` schema 对 135 条运行准入门（`scripts/promote_services.py`）：

- 严格模式（不构造步骤）：**135 条全部被拒**，原因是契约强制 `steps` 至少一项，而公开页没有
  办理步骤。这说明"没有步骤就不该进事务集合"是契约本身的硬约束，不是数据采集缺陷。
- `--allow-navigation-step` 模式：135 条全部通过。该步骤是**导航步骤**，明确写有
  "办事大厅未公开该事项的内部办理流程；本页仅登记公开的办理入口与指南信息"，不冒称办理流程。

因此事务集合的采纳需先决定：接受`导航步骤`（可入库 135 条，诚实标注），还是等公开的部门
办事指南补齐真实步骤（步骤级来源目前被 412 阻断）。产物见同目录
`services_admitted.json` 与 `services_rejected.json`。

### 本地版本与线上版本分开记录

`data/cdut/rag/current.json` 指向 `kb-229ee34eba99ef34`（176 sources，2026-10-14 生成），
而 `README.md` 与线上基线记录 `kb-f08fa4fd8b583700`（158 sources，2026-10-11b）。
2026-10-21 本地核验仍读取 `kb-229ee34eba99ef34`（176 sources、322 chunks）；
有效 `current.json` 优先于配置的备用 bundle。本轮不改发布指针，不能据本地版本推断线上状态。
线上证据以 [LIVE_BASELINE](LIVE_BASELINE.zh-CN.md) 为准。

### 2026-10-21 学生生活修正候选

DeepSeek 前轮增量涉及教学作息、食堂、住宿调整、家属区维修、档案、校园卡、图书馆、
2026 下半年四六级、机电工程学院奖助学金。9 条旧查询记录已按原件修正并导入 `knowledge.json`；
这不等于 RAG 发布。

`rag/packages/student-life-integrated-20261021-v2/` 保存修正后的 32 个候选片段、12 份原件或
供应商文字提取，以及文件/URL/哈希关联；未把文字提取称为学校原始 HTTP 响应。
`rag/candidates/student-life-integrated-20261021-v2/` 为修正候选，184 sources、354 chunks。
它完整保留本地当前版本的 176 sources、322 chunks 和 93 份已绑定原文文件，新增 8 个来源、32 个片段。
候选仍 pending，尚未生成新向量或通过正式知识发布门槛；已有线上和本地发布版本均未切换。

修正包括奖助学金资格、处分和兼得例外、不同评审学年；家属区报修与学生宿舍分离；
教学表不能证明公寓熄灯；图书馆续借来源绑定；旧校园卡保留时效提醒，校园网上网账号表述差异待核对。
原文核验、冲突与缺口见[报告](qa/student-experience-20261021.md)。新生采集由用户的 DeepSeek
继续执行，独立[交付契约](../data/cdut/rag/packages/freshman-candidate-20261021/TASK.md)不修改应用。

### 其他站点采集现状

`www`、`wxc`、`aao`、`xsc`、`lib` 等站点由瑞数动态挑战保护，纯 HTTP 与本地浏览器渲染均
返回 412/400，无法在不绕过访问控制的前提下采集。这些站点的通知与办事指南为避免触及该边界，
暂不自动采集；如需纳入，应通过经批准的采集通道（例如在合规浏览器中人工另存后导入），
保持"源站访问失败不绕过访问控制"的原则。

上述为早期直连采集记录。2026-10-21 独立 Search/Fetch 已实际取得部分学校网页正文；
其供应商提取与原始直连分开标注，失败响应、摘要和搜索结果列表仍不作为事实正文。
