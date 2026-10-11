# CampusPilot 待审核知识包 — pending-20261011-wechat

状态：待审核。全部 source/chunk 的 verification_status 为 "pending"，reviewer 为空，verified_at/approval_id 为 null。
Schema：沿用 approved-20261010/raw/data 的 sources.json / chunks.jsonl，并加入 pending-20261011 的扩展字段（audience、valid_period、covered_topics、stale、stale_note、temporal_status、excluded_from_retrieval、char_count、below_min_length、related_topics 等）。另外每个 source 都有 content_origin 字段。
content_origin 统一为："wechat official account via wechat-catcher bot (user-provided link)"。access_method 为 user_provided_wechat_link。

输入：/workspace/wx_*.md（wechat-catcher 生成的 markdown），原文件已复制到 browser-raw/wechat/。图片在 /workspace/wx/<id>/images/。三篇缴费类文章的图片已做 OCR（见下方“图片OCR”）；其余文章图片未 OCR。
清洗：去掉纯图片行、编辑/排版署名、"更多活动动态"等固定尾巴和装饰性序号；保留步骤、链接和表格。
分块：按段落合并，目标 300–600 字。正文短或在分段边界处的 chunk 会更短（below_min_length=true），没有补字。
排除（未收录）：wx_ow8CdoaUQ0Q2TGRBmTZnmA（2021 教工报销），wx_Dsgv-mCB--_eKsipKJkPMQ（荐书）。
时效（以 2026-10-11 为准）：clubfair2026 已过期（活动日期 9/19–20）；tworgs2026 可能过期（见面日期 8/31 已过）；fresh2026fee 和 fee20262027 部分时间节点已过（建议缴费日期 9/14，缓缴申请截止 7/30），但医保代收截止日 12/20 仍在有效期内；两场就业活动（10/13、11/13）尚未举行，标为 current。
再生成：python3 build.py（只写入本目录）。

## 图片OCR（2026-10-11 补充）
工具：rapidocr-onnxruntime（中文），动图取首/中/末帧；每张有效图片均已人工查看原图核对数字、日期、金额、账号。看不清的值写 [无法识别]，未猜测。
- fee20262027（wx_mVGytkIE_8J4o5IliHFGaA）：32 张（去重后 11 张），全部为装饰性边框/插画动图/页尾横幅，无有效文字，未新增 chunk。
- fresh2026fee（wx_37b1EidELwZnhfLEiCDtjA）：20 张，14 张含有效文字（图004–015、017、018），新增 3 个 chunk（ocr01–ocr03）。
- feeinvoice（wx_BZ85K3YUUEtcyf7SqGl0ZA）：12 张，9 张含有效文字（图003–011），新增 1 个 chunk（ocr01）。
OCR chunk 字段：kind=official_image_ocr，content_origin="OCR of image in wechat article (manually checked)"，ocr=true，image_files=原图路径列表；verification_status 仍为 pending。只收录正文里没有的信息（截图界面文字、菜单路径、示例页面），截图中的个人姓名/学号/身份证、示例票据号不收录。截图多为往年示例（2020–2021），其中金额仅为演示，chunk 内已注明。
[无法识别]：fresh2026fee:ocr02 中学校统一社会信用代码、建行双建路支行开户账号（截图模糊）。
OCR 数据在 ocr_chunks.json，build.py 会一并生成。
合计：8 个来源，26 个 chunk（正文 22 + OCR 4）。
