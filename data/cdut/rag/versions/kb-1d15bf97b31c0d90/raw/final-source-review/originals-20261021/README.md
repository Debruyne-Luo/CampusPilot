# 两份历史原件：2026-10-21

用于正式发布验收的两份缺失正文。**只保存公开通知正文，不保存成绩截图中的课程/成绩记录。**

## 1. 2026-2027 学年第一学期选课通知

| 项目 | 值 |
|---|---|
| 官方页面 | https://aao.cdut.edu.cn/info/1171/7107.htm |
| 发布单位 | 成都理工大学教务处 |
| 落款 | 2026-06-26 |
| 原 PDF | [`select-20262027.pdf`](select-20262027.pdf) |
| PDF SHA-256 | `a55c63d0f0f1821f75156875bd01cbd3220cc48a0b476e813eb2fab0452be662` |
| 正文整理 | [`2026-2027-1-course-selection.md`](2026-2027-1-course-selection.md) |
| 正文 SHA-256 | `1987d2425a28447a78155fde92a6bc34ba6f8858bea95a57e5b513aa18bbbd45` |
| 本地文字来源 | `data/cdut/rag/packages/approved-20261011/chunks.jsonl` 的 `cdut:chunk:select20262027:bs01/bs02`（`exact_official_text_browser_save_by_user_embedded_pdf`） |
| 包内说明 | `data/cdut/rag/packages/approved-20261011/sources.json` 的 `cdut:source:select20262027` 记录了 `browser-raw/select-embedded.pdf` 与保存页 |

说明：网页本身只返回标题/导航，正文在页面内嵌 PDF 中。原 PDF 已从公开 `/__local/` 地址下载；
PDF 文字提取受字体编码影响，直接提取可能是乱码，因此正文用包内两段精确文本拼接。PDF 与两段
文本的标题、轮次、日期、注意事项一致。

## 2. 期末考试课程成绩复核的申请流程（“两周”口径）

| 项目 | 值 |
|---|---|
| 官方页面 | https://aao.cdut.edu.cn/info/1187/6963.htm |
| 发布单位 | 成都理工大学教务处 |
| 页面日期 | 2026-03-16 |
| 正文整理 | [`grade-review-2026.md`](grade-review-2026.md) |
| 正文 SHA-256 | `15f8eb0f6187e88f9199b8d2a197b83ed3712d8d23d6476952080bd10b4eba7a` |
| 截图 URL | https://aao.cdut.edu.cn/__local/0/C8/F7/3EFAE29D4F8D62D2A41139609A7_81B97993_A478.png |
| 截图 SHA-256 | `e53457dc49d876d9d3c5681a91e39442b88d13e92952b8c226fe66c8f54b69f0` |

说明：页面正文明确写“成绩公布 **2 周内**（过期不再受理）”，由学生本人在教务管理系统
“考试管理”提交查卷申请并上传书面材料。页面内嵌截图包含一条课程/成绩记录，**未复制进
仓库**；本目录只保存文字正文。

## 与既有条目的冲突

- `学籍管理办法`（2019）第二十五条：成绩公布后 **10 个工作日**内提出书面复核申请。
- 本页（2026-03-16）：成绩公布后 **2 周内**（过期不再受理）。

两者可能是“制度口径 vs 当前系统流程”的差异；2 周是 14 个自然日，10 个工作日通常也接近
14 天，但边界不同。**未解决，保持 OPEN**。发布前应由教务处/学籍管理科室确认；在此之前
回答应同时提示“以当学期通知/教务系统为准”，不能只写一个数字。

见 [知识库冲突清单](../../KNOWLEDGE_CONFLICTS_20261021.zh-CN.md) 第 9 项。

## 目录

- `select-20262027.pdf`：选课通知原始 PDF
- `2026-2027-1-course-selection.md`：选课通知正文
- `grade-review-2026.md`：成绩复核“两周”正文
- `README.md`：本文件
