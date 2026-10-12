# CDUT public source inventory

2026-10-09 按用户本次要求补充校园生活与地图目录：现有 40 个地点、32 个高德
建筑/店铺参考点，全部保留 `needs_review`。网安楼按用户同楼说明关联生态环境学院
点位，王洪辉官网办公室原文关联该建筑；不确认老师当前在场或室内入口。东教 E1A、
E1B、E2A、E2B、E2C 分别收录，可检索教室号；E1B/E2A/E2B/E2C 独立坐标仍为空。
补卡地点加入银杏，保留余额大于20元及设备卡种限制。芙蓉/珙桐品牌餐饮、东苑
餐饮与菜鸟/京东/顺丰可检索。来源明确区分学校官方、高德 API 与当次用户补充；
用户补充没有公开 URL，不能用它证明费用、开放时间或学校政策。
新增条目与隐私/推荐契约见 [API contract](../../docs/API_CONTRACT.md)。

下文的 2026-10-07/08 数量与未关联状态是历史基线，本段描述当前目录。

2026-10-07 的提交版增量依据用户批准的 [ADR 0004](../../docs/adr/0004-submission-web-map-and-dify.md)。
现在包含 4 项事务、3 个部门、20 个地点候选、5 位计算机与网络安全学院教师和 13 条来源证据。
新增 `places.json`、`teachers.json`。全部资料仍 `needs_review`。
2026-10-08 本地增量为 14 个地点添加高德 GCJ02 建筑坐标候选，6 个仍为 `null`，
0 个坐标获人工确认，未开放导航。用户已部署该快照，完整 API 记录与网页字节检查通过。
高德坐标依据独立于校园业务来源；
导入清单、排除理由及可复现查询记录见
[地图候选核对清单](../../docs/MAP_CANDIDATE_REVIEW.zh-CN.md)。
王洪辉的官网文本列出网安楼 204 室，但校区、建筑关联和当前办公室未确认，`place_id=null`。
其他 4 位办公室未收录。学生补卡指引取自 2024 年指南；2026 年寒假自助区名单仅作核验线索，
未把旧通知的卡种、设备状态或值班时间当成 10 月现行规则。详细清单与录入方法见
[提交版资料核验](../../docs/SUBMISSION_DATA.zh-CN.md)。

以下保留 Issue #2 原始三事务来源说明，新增记录不改变其原有出处。

**CONFIRMED:** Tech Lead approved Stage A and implementation for exactly three matters:
campus card loss reporting, graduate enrollment proof, and tuition electronic receipts
for the 2026–2027 academic year. These are source-backed records, not synthetic fixtures.
**All records and sources remain `needs_review`.** Acceptance of the inventory does not
verify current university procedures. Independent Muse QA and source review remain pending.

## Files and sources

- `services.json`: the three services, conditional procedures, limitations and field provenance.
- `offices.json`: three responsible department entries. All physical locations and office hours
  are unknown (`null`). A department name is not a claim about a service counter or printer.
- `sources.json`: four SourceEvidence entries, including the limited 2026 platform corroboration.

| Evidence | Official URL | Scope / version |
| --- | --- | --- |
| `cdut:evidence:card-guide-2024` | [Student guide PDF](https://wxc.cdut.edu.cn/__local/8/1C/3C/0F34CEA8E563BE8802193833FE4_CFB792C4_36A72F.pdf) | Network and Information Office; fourth edition, August 2024; printed pp. 25, 29, 34 (PDF pp. 28, 32, 37) |
| `cdut:evidence:graduate-proof-2023` | [Canonical graduate notice](https://gra.cdut.edu.cn/info/1007/5283.htm) | Graduate School; 2023-09-12 trial notice, sections 1–3 and 5 |
| `cdut:evidence:credential-platform-2026` | [2026 winter information-service notice](https://wxc.cdut.edu.cn/info/1006/3954.htm) | Network and Information Office; 2026-01-29, section 4.1; platform existence only |
| `cdut:evidence:tuition-receipt-2026` | [2026–2027 payment notice](https://jcc.cdut.edu.cn/info/1012/2724.htm) | Finance Office; page published 2026-06-30, body signed 2026-06-29; receipt section 3 |

Collected on 2026-09-27. Source authority (`official_department`) is separate from verification.
Publication, last update, retrieval and verification dates are independent. Unknown dates stay
null; the card guide's month-level cover date is preserved in `version`, not invented as a day.

## Card-guide prerequisite and access evidence

The current [Network and Information Office homepage](https://wxc.cdut.edu.cn/) could not be
read directly by the agent (HTTP 412; browser connection also failed). In response to the request
for its current guide, the Tech Lead supplied the PDF and explicitly confirmed that it came from
the current homepage guide link. Local text extraction confirmed the cover and cited chapters;
it is the same August 2024 fourth edition as Stage A E1. No newer version was supplied or established.

The supplied file's SHA-256 is
`825729937cfd2791c768c2682d1bc1ac41b57a4a6ded57033b0de63f419239b9`.
Its original filename is `0F34CEA8E563BE8802193833FE4_CFB792C4_36A72F.pdf`.
The PDF itself and the operator's local path are not needed at runtime and are not committed.
The homepage linkage is human-confirmed, not claimed as an automated live-site check.
This confirmation does not mark service facts verified.

The graduate and finance pages returned HTTP 412 on direct access. Their official-page search
index text was used; `access_method=search_index` makes that limitation visible. The canonical
graduate URL is the reviewed `/info/1007/5283.htm`, not its alternate category URL.

## Interpretation and review rules

- `null` means unknown/unconfirmed, never “none required”. An empty list would mean an explicitly
  sourced absence and also requires provenance. The current records do not invent such absences.
- IDs are project-assigned; aliases are project search labels grounded in the named service.
  `FieldEvidence.note` distinguishes these labels from official terminology.
- The 2026 source only corroborates that the credential platform is listed. It cannot support
  the 2023 application frequency, fees, printer location or current validity. Old rules remain
  labeled as trial-notice statements and `needs_review`.
- Receipt guidance is explicitly scoped to `2026-2027`. The 24-hour rule covers only WeChat/web
  payments stated in the notice, not Alipay. Loan timing preserves its separate conditions.
- Unknown printer/counter locations stay null. Website footers, outdated holiday rosters and
  campus-wide addresses are not substitutes for a verified service location.
- CampusPilot only returns instructions and public sources. No account credentials, student IDs,
  receipts or application contents are collected; no login, signing, payment or loss reporting runs.

To update: inspect the official source, compare issuer/scope/version and affected fields, update
the smallest source and field mappings, preserve uncertainty, run the README checks, and submit
for human review/Muse QA. A newer timestamp does not resolve conflicting applicability by itself.
Do not switch any seed to verified merely because tests pass. SourceEvidence can describe a
human verification with reviewer/date, but this phase's directory records only accept needs_review;
there is no verification or publication workflow implemented.

**OPEN:** designated ongoing source reviewer, refresh cadence/expiry rules, current trial-rule
validity, missing physical office fields and publication readiness. Future reviewed publication
needs a separate contract/workflow change. No automated refresh, scraping or database is introduced.

## Reproduce

Commands are in the [root README](../../README.md#run-and-verify). Run from the checkout root or
pass an explicit `--data-dir`. JSON snapshots are loaded entirely before queries are exposed;
invalid records/references fail loading. Source URLs are citations only, never fetched at runtime.
The demo uses only `campuspilot.mocks` and does not load this directory or fall back to it.
