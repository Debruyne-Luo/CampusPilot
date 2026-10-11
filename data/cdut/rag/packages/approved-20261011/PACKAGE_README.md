# CampusPilot pending knowledge package — 2026-10-11

Status: PENDING. Every source and chunk has verification_status "pending", an empty reviewer, and null verified_at/approval_id. Nothing here is approved until 宇豪 reviews it.
Files: sources.json (129 after teacher merge), chunks.jsonl (209; teacher_lookup chunks regenerated from merge), coverage.md / coverage.csv (42 topics), teachers/teachers.csv+json plus teachers_merged.csv/json/xlsx. Schema follows approved-20261010/raw/data. Added fields on each source: `audience` (适用对象), `valid_period` (有效期), and `covered_topics` (only filled for the multi-topic 学籍管理办法 source; null elsewhere).

## Access problems
- Every *.cdut.edu.cn HTML subsite I tried (aao, xsc, clhq, lib, wxc, www, bwc, xljk, hospital…) returned HTTP 412, which is an anti-bot JS challenge. This happened both from the box and from the fetch service. I did not try to get around it. gs/xyy/cwc/hq gave no response or have no such host.
- weixin.sogou.com redirected to its antispider page. No WeChat articles were collected.
- Static PDFs under /__local/ downloaded fine. That is where the full text of 学籍管理办法 (成理校教〔2019〕18号) came from.

## Caveats
- content_origin tells you how reliable a chunk is:
  - official_full_text_extract: exact text from the official PDF.
  - search_index_snippet_of_official_source: a snippet from a search engine's copy of an official page.
  - search_engine_summary_needs_manual_check: a search-engine summary. Check every number, phone and place before approving.
- Many snippet chunks are under 300 characters because only the title or snippet could be read. The chunks were not padded.
- Several sources are college-level (学院) pages, not university-level ones (机电、计算机、能源、管理科学).
- cdut:source:lyfwdorm has the same URL as the approved cdut:source:repair. Consider merging them.
- Pages from third-party sites, other universities, and 工程技术学院 (a separate institution) were not used as sources.
- Unknown dates and validity periods were left null. Nothing was invented.

## Update 2026-10-11 — browser-saved pages (official text)
Input: `browser-raw/cdut-pages.zip` (Windows Ctrl+S "complete" saves by 宇豪). Filenames were GBK; extracted with cp437→gbk decoding into `browser-raw/pages/` (Windows `\` paths converted; 2 over-long names shortened with a hash suffix, see `browser-raw/extract_name_map.json`). Original URLs come from each file's "saved from url" comment.

- 22 main HTML pages: 18 official article/service pages with text, 2 pages with no article text (失物招领, 能源学院开题答辩用表), 2 砚湖易办 portal pages (login UI and a personal centre showing a user name; navigation only, **not ingested** for privacy and because there is no content). There was also an orphan `教务科-成都理工大学环境与土木工程学院_files` folder with no HTML page.
- The 选课 page held only a PDF.js viewer. Its body is the embedded PDF `/__local/8/F0/A1/9E9AD568275799D8BD7C75F2969_53A09504_204C4.pdf`, which I downloaded from the public URL into `browser-raw/select-embedded.pdf` (content_origin `..._embedded_pdf`).
- Attachments referenced but not saved: 档案馆2023 附件1–3 (pdf/xlsx), 机电2026离校日程 .doc, 楼寓外专楼住宿申请表 .doc, 计网勤工助学 申请表 (Baidu pan link). No PDFs or attachments were inside the _files folders.

Chunk changes:
- Snippet/summary chunks of saved sources were replaced by exact official text: 85 chunks, content_origin `exact_official_text_browser_save_by_user`, target 300–600 chars. A few chunks are shorter because the whole page is short or because of a split boundary; these are flagged `below_min_length`. Nothing was padded.
- Sources not saved (summer2026hq, aaoguides), plus saved pages that had no body (lostfound, gradthesis): their old snippet chunks are kept with `excluded_from_retrieval: true` and an `exclusion_reason`.
- The 学籍管理办法 PDF chunks (16, official PDF text) are unchanged.
- Totals: 101 retrievable official chunks, 4 excluded.
- New chunk fields: `excluded_from_retrieval`, `exclusion_reason`, `char_count`, `below_min_length`, `stale_source`, `related_topics` (multi-topic guide pages are keyword-tagged). New source fields: `stale`, `stale_note`, `browser_saved_file`, `is_new_in_browser_save`.
- Edits to the page text: nav, footers, view counters, decorative lines and image captions were stripped. 计网勤工助学 page repeats section 六 verbatim; I kept one copy. 机电转专业 rows naming students (name + partial student ID) were left out of the chunks.

New sources: cet2026h1 (四六级, news.cdut), cistfresh2024 + cistfresh2025 (计网学院新生指南), lyzn2023 (楼寓中心服务指南).

Timeliness (today 2026-10-11): temporal_status was set from the page dates. stale=true on 14 sources: select20262027, transfer2026, mee2025grant, loanconfirm2026, cistwork2025, psych2026, medins2026, summer2026hq, dagtransfer2023, meeleave2026, clubaudit2024, cet2026h1, cistfresh2024, cistfresh2025. Nothing was deleted. Each stale source has a stale_note explaining why.

Conflicts to check: 餐厅 count is 7 (2024 guide) vs 6 (2025 guide). 公寓 count is 28 (guides) vs 29 (2023 楼寓指南). 楼寓 office is 101-104 (2023) vs 102 (current lyfw page).

Everything is still verification_status "pending" with an empty reviewer. The approved directory and the code were not touched.

## Update 2026-10-11 (round 2): `browser-raw/cdut-round2.zip`
Extracted to `browser-raw/round2/` with Python, decoding the names as cp437→gbk. No names needed shortening. `round2_name_map.json` is empty.

PART A (notices and service pages). 9 HTML pages outside teachers/:
- Ingested 1 page: 关于2026-2027学年第一学期公共选修课申报的通知 (aao/info/1171/7023.htm, 教务处, 2026-04-28; the signature line is dated 2026-04-29). It is addressed to 各单位/学院 and the teachers who open courses, not to students. It went in as `cdut:source:pubelective20262027` under topic course_selection, with 2 chunks. It is stale: the submission deadline was 2026-05-17 18:00.
- Skipped for privacy (logged-in pages showing 罗宇豪's name or account data): 学生请假 (xgfw 我的请假), 成都理工大学教务系统 (jw 学生主页), 砚湖易办 (个人中心).
- Skipped because they have no article text (list or portal pages only): 教务处首页, cist 通知公告 list, cist 团学风采 list, faculty 教师索引 (filter tree only, no teacher names).
- A second copy of 胡亨琪's homepage at the zip root is the same as the teachers/ copy apart from the visit counter. It is used in Part B.
- No new 四六级, 医保 or 2026 新生指南 page, so no supersedes links were added.

PART B (teachers): `teachers/teachers.csv` (UTF-8 BOM) and `teachers/teachers.json` (adds intro_text).
- The cist 教师名录 lists 100 people. 胡亨琪 appears 4 times there and was deduped. Two more teachers (李军, 王忠桃) have saved homepages but are not in the directory, so there are 102 rows.
- Rules for fields: values come only from the saved pages. `title` is taken from the homepage text when it is stated there. Otherwise it is the directory category, and `title_source` records which. `directory_profile_url` holds the cist /info/1231/ link (that page was not saved). Public emails were kept. No phone numbers appear on any saved page.
- Added 26 sources: `cdut:source:cistteacherdir` plus 25 `cdut:source:faculty-*`. Added 102 chunks with topic teacher_lookup and content_origin `structured_profile_from_official_page_fields_plus_exact_intro_text`. Teachers without a homepage get a chunk built from name and category only, pointing at the directory source.
- Conflicts to check: 罗耀华's homepage says 副高, but the directory lists him as 正高级. 范鹏's homepage says 讲师, but the directory lists him under 校聘副高级. 孙伟恒's intro says 计算机科学与技术学院.

## Update 2026-10-11 — merge user teacher roster (B) into round-2 teachers (A)

Input B: user-provided xlsx (`教师名录` 94 rows with 姓名/职称类别/公开邮箱/办公楼/房间号/个人电话/研究方向/个人官方网页/审核状态/证据类型/名录来源/核验日期/备注; plus `部门联系方式` and `采集说明`). Matched to A (`teachers/teachers.csv`+`.json`, 102 rows from saved faculty.cdut.edu.cn homepages + cist directory) by exact 姓名.

Outputs (under `teachers/`):
- `teachers_merged.csv` (UTF-8 BOM), `teachers_merged.json` (adds `intro_text` when A had it), `teachers_merged.xlsx` with sheets `教师名录`, `部门联系方式` (copied from B), `冲突`.
- Merged columns: name, title, title_source, email, email_source, building, room, office_source, phone, research_areas, research_source, enrollment_majors, cist_profile_url, faculty_homepage_url, in_directory, evidence_notes, source_files.
- Fill rule: take whichever side has a non-empty value; if both differ, keep **A** in the main column and list both on the `冲突` sheet. A’s known conflicts (罗耀华/范鹏 title; 孙伟恒 college wording) are carried on that sheet. No invented values. Department footer phones were not treated as personal phones (personal phone count stays 0).

Counts: **102** merged rows; **8** names only in A（任志愿、何苗、周宇、张频频、戴婉莹、杜洋、王忠桃、简继皓）; **0** only in B. Filled: email **31**, office(building/room) **8**, research_areas **33**, phone **0**. Conflicts sheet: **35** rows (mostly title wording A homepage vs B directory category; also 王洪辉 office/research, 多滨/李军 research, 吴媛媛/唐源 cist_profile_url 2020 vs directory link, 孙伟恒 college).

Chunks/sources:
- Replaced all 102 `topic_id=teacher_lookup` chunks from the merged table; `chunk_id` values kept stable (`cdut:chunk:teacher:{姓名}`). `content_origin` is now `structured_profile_from_merged_roster_and_official_page_fields`.
- Added **79** pending sources for cist profile URLs (`cdut:source:cistprofile-{栏目}-{id}`), including the two B-only 2020 pages (`info/1118/3710` 吴媛媛, `info/1118/3709` 唐源). Those two teachers’ chunks have `stale_source=true` and email/research text notes that 2020 data may be outdated.
- sources.json total **129**; chunks.jsonl still **209** (107 non-teacher + 102 teacher).
