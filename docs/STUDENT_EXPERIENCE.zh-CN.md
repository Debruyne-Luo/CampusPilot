# 新生体验实施与运行说明

最终知识与 RAG 已于本地启用 `kb-1d15bf97b31c0d90`，保留本页对话和清单体验。
正式知识、实际答题门槛、手机复核及未达标时延见
[最终交付记录](qa/final-knowledge-20261021.md)；下文的早期候选和测试记录保留其原阶段含义。

2026-10-21 用户批准的本地实现。工作区为 `CampusPilot-integration`，基线为
`715555e13829395aeef4abb89706f3f6a3f9d51a` 加实施前已有修改。保留此前 Harness²、Jev、地图、
清单与模型资产；本轮没有推送、合并、部署或录制视频。

## 对话行为

- 默认先给简短结论、线上入口或线下地点，保留身份、余额、学年与必要例外。没有网址的小程序
  给准确名称；官方指南与直接办理入口采用不同按钮，不保证平台正在受理。
- 完全匹配的目录地点、已知办理渠道和明确只问网址的受核验事项可直接返回，避免模型和联网等待。
  组合问题、附近的其他目标、其他校区、资格、费用、时效及材料问题继续正常理解与核对。
- 普通网页使用 `concise=True`。`AgentRunner` 的默认参数保持旧实验兼容，已有 Harness² 对照记录
  不重算成新体验收益。精确入口经同一工具权限边界、适用范围和原件关联校验，只省去嵌入等待。
- “要带什么材料”等短追问接续当前事项；切换地点话题会清理事项焦点。只有请求材料/步骤/清单时
  才生成清单，模型也不能擅自调用清单工具。保存格式不变，新对话及刷新保留准备进度。
- 处理进度来自实际工具事件，完成后折叠。材料、步骤、全部来源按需展开；手机回答卡片保持完整
  高度，通过对话区域滚动阅读。没有新增公共 API。
- 按用户后续要求，主界面移除实验室入口和阅读设置，不再加载或保存字号/动效偏好；仍尊重系统
  的减少动效设置。回答不自动追加“适用提醒”，具体业务条件由正文表达，来源范围保留在证据元数据中。

## 联网与知识边界

使用现有 `CAMPUSPILOT_WEB_SEARCH=on`、DeepSeek Key 和证据预算配置，详见
[EVIDENCE_MEDIA](EVIDENCE_MEDIA.zh-CN.md#配置与费用)。独立 Search 请求正文；缺正文才 Fetch，
共享十秒期限，至多两次搜索、三页读取。明确失败/空结果、超时、预算与部分成功分别记录。
Search 已给正文时不会再对源站抓一次；正文过长不截断当完整政策，搜索列表与防护页被拒绝。

本地不足、明确要求最新安排或疑难判断需要补证时联网。Jev 未确认的新网页只作为标注线索，
不能进入权威回答。需要最新安排而仅剩旧资料时，不展开旧批次日期。已知不同校区的网站先隔离，
其余身份、校区、学年与例外交给证据判断；不调低 Jev 置信门槛来让冒烟通过。

外部官方平台只有在白名单内且 URL 逐字出现在已采纳学校正文中，才能生成入口卡片；
来源 URL 仍须属于学校，含凭据、会话或不安全跳转的 URL 被拒绝。尚未核验可用性的入口继续标注。

修正知识包与 DeepSeek 采集分工见 [KNOWLEDGE](KNOWLEDGE.zh-CN.md#2026-10-21-学生生活修正候选)。
新候选叠加当前本地正式知识，完整保留其原件与入口关联；未以旧备用包替换当前知识。

## 复现与交付

在仓库根目录运行以下离线检查；Windows 测试使用 UTF-8。完整结果及已有 Windows 发布失败
见 [核验报告](qa/student-experience-20261021.md)。

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -q
.venv/Scripts/ruff.exe check backend/src tests scripts/build_student_life_candidate.py scripts/evaluate_student_experience.py
.venv/Scripts/mypy.exe backend/src tests scripts/build_student_life_candidate.py scripts/evaluate_student_experience.py
node --test tests/*.test.js tests/*.test.mjs
.venv/Scripts/python.exe -X utf8 scripts/evaluate_student_experience.py --output output/student-latency.json
```

候选可由以下脚本重建；它校验当前指针、原件哈希，既有同名候选内容不同时拒绝覆盖。
输入为用户前轮 DeepSeek 产物所在 checkout，不修改输入。

```powershell
.venv/Scripts/python.exe -X utf8 scripts/build_student_life_candidate.py --source-root D:/Projects/CampusPilot
```

真实冒烟需明确提供仓库外配置和**现有活动账本**目录；脚本复用 `CampaignBudget`，不重置预算。
配置中仅有 `deepseek_key_file`、`jev_key_file` 文件路径，密钥不写入仓库。该命令会实际消费 API。

```powershell
.venv/Scripts/python.exe -X utf8 scripts/evaluate_student_experience.py --output output/student-smoke.json --config D:/PRIVATE/experiment-config.json --budget-dir D:/PRIVATE/campaign-harness-jev-20261020
```

浏览器回归使用本地 phase2、词法知识与无模型服务，运行
`playwright-cli -s=student open http://127.0.0.1:8789/` 后执行
`playwright-cli -s=student run-code --filename tests/browser_student_experience.js`。
脚本使用独立浏览器上下文，不清理已有浏览器保存数据，也不访问外部办理平台。
本轮 Windows Python 3.14 本地服务使用 `asyncio.SelectorEventLoop`，避免本机 Proactor 的
`WinError 10014`；这是本地验收服务设置，不修改生产运行方式。

可审查差异、公开实测记录和源码指纹保存在
[`evaluation/student-experience-20261021/`](../evaluation/student-experience-20261021/)。
正式 RAG 采纳、完整回答质量与生产时延验收仍按原门槛执行，不以这些冒烟取代。
