# 知识包 2026-10-11 审核清单

审批：宇豪罗于 2026-10-11 约 11:48（UTC+8）在对话中确认“全部通过、保留私人邮箱”；审批记录 `data/cdut/rag/approved-20261011/raw/APPROVAL_RECORD.json`（approval_id CDUT-KB-APPROVAL-2026-10-11-01）。

来源 129 个；入库 chunk 205 个（排除 excluded_from_retrieval 4 个）；stale chunk 63 个（检索降权 ×0.5，引用时追加“可能已过期”）；教师 102 人（无电话）。browser-raw/ 未读取。

## 来源

| ✓ | source_id | 标题 | 单位 | 日期 | chunks | stale |
|---|---|---|---|---|---|---|
| [x] | `cdut:source:xjgl2019` | [关于印发《成都理工大学全日制普通本科学生学籍管理办法》的通知（成理校教〔2019](https://dbxb.cdut.edu.cn/__local/7/B6/E5/006AC04D88A214D1AD8B1F5E540_16B4A5B7_C543C.pdf) | 成都理工大学（教务处负责解释） | 2019-12-31 | 16 |  |
| [x] | `cdut:source:select20262027` | [关于2026-2027学年第一学期选课的通知](https://aao.cdut.edu.cn/info/1171/7107.htm) | 教务处 | 2026-06-26 | 2 | 是 |
| [x] | `cdut:source:transfer2026` | [机电工程学院2026年普通本科生申请转专业初审名单公布](https://mee.cdut.edu.cn/info/1049/3569.htm) | 机电工程学院 | 2026-04-03 | 1 | 是 |
| [x] | `cdut:source:zzzc` | [资助政策-成都理工大学学生处](https://xsc.cdut.edu.cn/zzgl/zzzc.htm) | 学生处 |  | 5 |  |
| [x] | `cdut:source:mee2025grant` | [成都理工大学机电工程学院2025年本专科生国家奖助学金评审工作实施细则](https://mee.cdut.edu.cn/info/1049/3327.htm) | 机电工程学院 | 2025-09-29 | 6 | 是 |
| [x] | `cdut:source:loanconfirm2026` | [2026届毕业生｜国家助学贷款毕业确认，请及时完成！](https://xsc.cdut.edu.cn/info/1033/4603.htm) | 学生处（信息来源：学生资助管理中心） | 2026-05-22 | 4 | 是 |
| [x] | `cdut:source:cistwork2025` | [2025-2026学年秋季学期计算机与网络安全学院（示范性软件学院） 勤工助学岗](https://cist.cdut.edu.cn/info/1143/7510.htm) | 计算机与网络安全学院（示范性软件学院）（页面：发布者 计网学院） | 2025-09-23 | 3 | 是 |
| [x] | `cdut:source:psych2026` | [2026年春季学期学生心理咨询服务通知](https://xljk.cdut.edu.cn/info/1072/3594.htm) | 心理健康教育中心 | 2026-03-05 | 1 | 是 |
| [x] | `cdut:source:medins2026` | [2026年成都理工大学学生城乡基本医疗保险购买须知](https://hospital.cdut.edu.cn/info/1085/2644.htm) | 校医院 | 2025-10-14 | 3 | 是 |
| [x] | `cdut:source:hospoverview` | [医院概况](https://hospital.cdut.edu.cn/yygk.htm) | 成都理工大学医院 |  | 2 |  |
| [x] | `cdut:source:summer2026hq` | [关于2026年暑假后勤保障工作安排的通知](https://clhq.cdut.edu.cn/info/1087/5194.htm) | 后勤保障部 |  | 0 |  |
| [x] | `cdut:source:libprint` | [自助文印体验-成都理工大学图书馆](https://lib.cdut.edu.cn/fw/ssfw/zzwyty.htm) | 图书馆 |  | 1 |  |
| [x] | `cdut:source:lostfound` | [失物招领-成都理工大学后勤保障部](https://clhq.cdut.edu.cn/fwdt1/swzl.htm) | 后勤保障部 |  | 0 |  |
| [x] | `cdut:source:lyfwdorm` | [楼寓服务-成都理工大学后勤保障部](https://clhq.cdut.edu.cn/fwdt1/lyfw.htm) | 后勤保障部楼寓服务中心 |  | 8 |  |
| [x] | `cdut:source:dagtransfer2023` | [关于做好2023年毕业生 档案转递数据审核工作的通知](https://dag.cdut.edu.cn/info/1076/1753.htm) | 档案馆（校史馆） | 2023-06-16 | 2 | 是 |
| [x] | `cdut:source:meeleave2026` | [关于做好机电工程学院2026届毕业生文明离校工作的通知](https://mee.cdut.edu.cn/info/1049/3682.htm) | 机电工程学院 | 2026-05-27 | 1 | 是 |
| [x] | `cdut:source:clubaudit2024` | [关于公布成都理工大学2024年学生社团年度审核结果的公示](https://youth.cdut.edu.cn/info/1006/2681.htm) | 校团委 | 2024-07-05 | 2 | 是 |
| [x] | `cdut:source:gradthesis` | [开题、答辩用表-成都理工大学能源学院](https://energy.cdut.edu.cn/yjsjyy/bgxz/kt_dbyb.htm) | 能源学院 |  | 0 |  |
| [x] | `cdut:source:aaoguides` | [成都理工大学教务处首页（办事指南列表）](https://aao.cdut.edu.cn/index.htm) | 教务处 |  | 0 |  |
| [x] | `cdut:source:cet2026h1` | [2026年上半年全国大学英语四、六级考试报名通知](https://news.cdut.edu.cn/info/1005/52862.htm) | 外国语学院（发布于成都理工新闻网 news.cdut.edu.cn） | 2026-03-13 | 3 | 是 |
| [x] | `cdut:source:cistfresh2024` | [一键收藏！2024本科新生入学指南](https://cist.cdut.edu.cn/info/1135/7328.htm) | 计算机与网络安全学院（示范性软件学院）（页面：发布者 计网学院） | 2024-08-08 | 16 | 是 |
| [x] | `cdut:source:cistfresh2025` | [新成理人集合！速戳这份开学秘籍](https://cist.cdut.edu.cn/info/1135/7388.htm) | 计算机与网络安全学院（示范性软件学院）（页面：发布者 计网学院） | 2025-09-03 | 15 | 是 |
| [x] | `cdut:source:lyzn2023` | [楼寓中心服务指南](https://clhq.cdut.edu.cn/info/1037/2344.htm) | 后勤保障部（页面来源：后期服务集团；作者：刘俊丽） | 2023-01-06 | 10 |  |
| [x] | `cdut:source:pubelective20262027` | [关于2026-2027学年第一学期公共选修课申报的通知](https://aao.cdut.edu.cn/info/1171/7023.htm) | 成都理工大学教务处（页面：作者 教务处） | 2026-04-28 | 2 | 是 |
| [x] | `cdut:source:cistteacherdir` | [教师名录-计算机与网络安全学院（示范性软件学院）](https://cist.cdut.edu.cn/szdw/JSML.htm) | 计算机与网络安全学院（示范性软件学院） |  | 21 |  |
| [x] | `cdut:source:faculty-wanghonghui` | [王洪辉——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/wanghonghui/zh_CN/index.htm) | 成都理工大学教师个人主页平台（王洪辉本人维护） | 2026-10-06 | 1 |  |
| [x] | `cdut:source:faculty-zx1234567891011121314151` | [朱星——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/ZX12345678910111213141516/zh_CN/index.htm) | 成都理工大学教师个人主页平台（朱星本人维护） | 2026-09-29 | 1 |  |
| [x] | `cdut:source:faculty-duobin` | [多滨——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/duobin/zh_CN/index.htm) | 成都理工大学教师个人主页平台（多滨本人维护） | 2026-09-15 | 1 |  |
| [x] | `cdut:source:faculty-ldf12345` | [李冬芬——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/LDF12345/zh_CN/index.htm) | 成都理工大学教师个人主页平台（李冬芬本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-cgz` | [陈光柱——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/CGZ/zh_CN/index.htm) | 成都理工大学教师个人主页平台（陈光柱本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-lyh123` | [罗耀华——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/LYH123/zh_CN/index.htm) | 成都理工大学教师个人主页平台（罗耀华本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-hgx` | [黄光鑫——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/HGX/zh_CN/zdylm/317224/list/index.htm) | 成都理工大学教师个人主页平台（黄光鑫本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-cb12` | [蔡彪——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/CB12/zh_CN/index.htm) | 成都理工大学教师个人主页平台（蔡彪本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-lhj12` | [李红军——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/LHJ12/zh_CN/index.htm) | 成都理工大学教师个人主页平台（李红军本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-zhangpeng` | [张澎——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/ZhangPeng/zh_CN/index.htm) | 成都理工大学教师个人主页平台（张澎本人维护） | 2026-07-07 | 1 |  |
| [x] | `cdut:source:faculty-xiaochuantang` | [唐小川——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/xiaochuantang/zh_CN/index.htm) | 成都理工大学教师个人主页平台（唐小川本人维护） | 2026-10-01 | 1 |  |
| [x] | `cdut:source:faculty-wq12345` | [温泉——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/WQ12345/zh_CN/index.htm) | 成都理工大学教师个人主页平台（温泉本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-swy` | [单武扬——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/SWY/zh_CN/index.htm) | 成都理工大学教师个人主页平台（单武扬本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-huhengqi` | [胡亨琪——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/huhengqi/zh_CN/index.htm) | 成都理工大学教师个人主页平台（胡亨琪本人维护） | 2026-06-12 | 1 |  |
| [x] | `cdut:source:faculty-yangrui` | [杨锐——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/yangrui/zh_CN/index.htm) | 成都理工大学教师个人主页平台（杨锐本人维护） | 2026-10-10 | 1 |  |
| [x] | `cdut:source:faculty-xiaopeng` | [肖鹏——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/xiaopeng/zh_CN/index.htm) | 成都理工大学教师个人主页平台（肖鹏本人维护） | 2026-07-23 | 1 |  |
| [x] | `cdut:source:faculty-qiushilin` | [邱士林——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/qiushilin/zh_CN/index.htm) | 成都理工大学教师个人主页平台（邱士林本人维护） | 2026-06-24 | 1 |  |
| [x] | `cdut:source:faculty-zlz` | [张罗致——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/ZLZ/zh_CN/index.htm) | 成都理工大学教师个人主页平台（张罗致本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-fanpeng` | [范鹏——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/fanpeng/zh_CN/index.htm) | 成都理工大学教师个人主页平台（范鹏本人维护） | 2026-06-12 | 1 |  |
| [x] | `cdut:source:faculty-zhaopengbiao` | [赵鹏飙——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/zhaopengbiao/zh_CN/index.htm) | 成都理工大学教师个人主页平台（赵鹏飙本人维护） | 2026-09-15 | 1 |  |
| [x] | `cdut:source:faculty-sunweiheng` | [孙伟恒——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/sunweiheng/zh_CN/index.htm) | 成都理工大学教师个人主页平台（孙伟恒本人维护） | 2026-06-12 | 1 |  |
| [x] | `cdut:source:faculty-zcq1234` | [赵成强——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/ZCQ1234/zh_CN/index/268756/list/index.htm) | 成都理工大学教师个人主页平台（赵成强本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-jianjihao` | [简继皓——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/jianjihao/zh_CN/index.htm) | 成都理工大学教师个人主页平台（简继皓本人维护） | 2026-09-04 | 1 |  |
| [x] | `cdut:source:faculty-lj1234567891011121314151` | [李军——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/LJ1234567891011121314151617181920/zh_CN/index.htm) | 成都理工大学教师个人主页平台（李军本人维护） |  | 1 |  |
| [x] | `cdut:source:faculty-wzt` | [王忠桃——成都理工大学教师个人主页](https://faculty.cdut.edu.cn/wzt/zh_CN/index.htm) | 成都理工大学教师个人主页平台（王忠桃本人维护） | 2026-07-07 | 1 |  |
| [x] | `cdut:source:cistprofile-1118-3709` | [教师个人简介（cist）—唐源](https://cist.cdut.edu.cn/info/1118/3709.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1118-3710` | [教师个人简介（cist）—吴媛媛](https://cist.cdut.edu.cn/info/1118/3710.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7466` | [教师个人简介（cist）—蔡彪](https://cist.cdut.edu.cn/info/1231/7466.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7469` | [教师个人简介（cist）—陈楚寒](https://cist.cdut.edu.cn/info/1231/7469.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7470` | [教师个人简介（cist）—陈光柱](https://cist.cdut.edu.cn/info/1231/7470.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7471` | [教师个人简介（cist）—胡文艺](https://cist.cdut.edu.cn/info/1231/7471.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7472` | [教师个人简介（cist）—胡艳梅](https://cist.cdut.edu.cn/info/1231/7472.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7473` | [教师个人简介（cist）—黄于鉴](https://cist.cdut.edu.cn/info/1231/7473.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7481` | [教师个人简介（cist）—冷小鹏](https://cist.cdut.edu.cn/info/1231/7481.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7482` | [教师个人简介（cist）—李红军](https://cist.cdut.edu.cn/info/1231/7482.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7483` | [教师个人简介（cist）—李英毅](https://cist.cdut.edu.cn/info/1231/7483.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7484` | [教师个人简介（cist）—梅占勇](https://cist.cdut.edu.cn/info/1231/7484.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7485` | [教师个人简介（cist）—桑强](https://cist.cdut.edu.cn/info/1231/7485.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7486` | [教师个人简介（cist）—孙伟恒](https://cist.cdut.edu.cn/info/1231/7486.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7487` | [教师个人简介（cist）—汤影](https://cist.cdut.edu.cn/info/1231/7487.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7488` | [教师个人简介（cist）—唐源](https://cist.cdut.edu.cn/info/1231/7488.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 | 是 |
| [x] | `cdut:source:cistprofile-1231-7489` | [教师个人简介（cist）—王美玲](https://cist.cdut.edu.cn/info/1231/7489.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7490` | [教师个人简介（cist）—王淼](https://cist.cdut.edu.cn/info/1231/7490.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7491` | [教师个人简介（cist）—吴静](https://cist.cdut.edu.cn/info/1231/7491.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7492` | [教师个人简介（cist）—吴媛媛](https://cist.cdut.edu.cn/info/1231/7492.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 | 是 |
| [x] | `cdut:source:cistprofile-1231-7493` | [教师个人简介（cist）—杨丰铭](https://cist.cdut.edu.cn/info/1231/7493.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7494` | [教师个人简介（cist）—杨国城](https://cist.cdut.edu.cn/info/1231/7494.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7495` | [教师个人简介（cist）—余展](https://cist.cdut.edu.cn/info/1231/7495.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7496` | [教师个人简介（cist）—张罗致](https://cist.cdut.edu.cn/info/1231/7496.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7497` | [教师个人简介（cist）—赵川](https://cist.cdut.edu.cn/info/1231/7497.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7498` | [教师个人简介（cist）—朱星](https://cist.cdut.edu.cn/info/1231/7498.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7552` | [教师个人简介（cist）—杨锐](https://cist.cdut.edu.cn/info/1231/7552.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7563` | [教师个人简介（cist）—邓飞](https://cist.cdut.edu.cn/info/1231/7563.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7564` | [教师个人简介（cist）—范鹏](https://cist.cdut.edu.cn/info/1231/7564.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7566` | [教师个人简介（cist）—胡英](https://cist.cdut.edu.cn/info/1231/7566.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7567` | [教师个人简介（cist）—李进凯](https://cist.cdut.edu.cn/info/1231/7567.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7568` | [教师个人简介（cist）—廖晓鹃](https://cist.cdut.edu.cn/info/1231/7568.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7569` | [教师个人简介（cist）—刘恒](https://cist.cdut.edu.cn/info/1231/7569.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7570` | [教师个人简介（cist）—李军](https://cist.cdut.edu.cn/info/1231/7570.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7571` | [教师个人简介（cist）—王立](https://cist.cdut.edu.cn/info/1231/7571.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7572` | [教师个人简介（cist）—王宇](https://cist.cdut.edu.cn/info/1231/7572.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7574` | [教师个人简介（cist）—宁进](https://cist.cdut.edu.cn/info/1231/7574.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7575` | [教师个人简介（cist）—荣莹](https://cist.cdut.edu.cn/info/1231/7575.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7576` | [教师个人简介（cist）—谭炜](https://cist.cdut.edu.cn/info/1231/7576.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7577` | [教师个人简介（cist）—唐云](https://cist.cdut.edu.cn/info/1231/7577.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7578` | [教师个人简介（cist）—王琛](https://cist.cdut.edu.cn/info/1231/7578.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7579` | [教师个人简介（cist）—吴旭](https://cist.cdut.edu.cn/info/1231/7579.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7580` | [教师个人简介（cist）—张芬](https://cist.cdut.edu.cn/info/1231/7580.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7581` | [教师个人简介（cist）—赵成强](https://cist.cdut.edu.cn/info/1231/7581.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7582` | [教师个人简介（cist）—多滨](https://cist.cdut.edu.cn/info/1231/7582.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7583` | [教师个人简介（cist）—刘楠](https://cist.cdut.edu.cn/info/1231/7583.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7584` | [教师个人简介（cist）—肖鹏](https://cist.cdut.edu.cn/info/1231/7584.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7585` | [教师个人简介（cist）—杨颖](https://cist.cdut.edu.cn/info/1231/7585.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7586` | [教师个人简介（cist）—周清](https://cist.cdut.edu.cn/info/1231/7586.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7587` | [教师个人简介（cist）—邱士林](https://cist.cdut.edu.cn/info/1231/7587.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7588` | [教师个人简介（cist）—张辉](https://cist.cdut.edu.cn/info/1231/7588.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7589` | [教师个人简介（cist）—赵鹏飙](https://cist.cdut.edu.cn/info/1231/7589.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7590` | [教师个人简介（cist）—钟豪](https://cist.cdut.edu.cn/info/1231/7590.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7591` | [教师个人简介（cist）—周让](https://cist.cdut.edu.cn/info/1231/7591.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7607` | [教师个人简介（cist）—王洪辉](https://cist.cdut.edu.cn/info/1231/7607.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7608` | [教师个人简介（cist）—李冬芬](https://cist.cdut.edu.cn/info/1231/7608.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7609` | [教师个人简介（cist）—张阳](https://cist.cdut.edu.cn/info/1231/7609.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7610` | [教师个人简介（cist）—赵仕波](https://cist.cdut.edu.cn/info/1231/7610.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7611` | [教师个人简介（cist）—黄光鑫](https://cist.cdut.edu.cn/info/1231/7611.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7624` | [教师个人简介（cist）—胡亨琪](https://cist.cdut.edu.cn/info/1231/7624.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7635` | [教师个人简介（cist）—单武扬](https://cist.cdut.edu.cn/info/1231/7635.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7636` | [教师个人简介（cist）—姚光乐](https://cist.cdut.edu.cn/info/1231/7636.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7637` | [教师个人简介（cist）—徐晓宇](https://cist.cdut.edu.cn/info/1231/7637.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7638` | [教师个人简介（cist）—陈才华](https://cist.cdut.edu.cn/info/1231/7638.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7639` | [教师个人简介（cist）—杨冬营](https://cist.cdut.edu.cn/info/1231/7639.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7640` | [教师个人简介（cist）—庞璐](https://cist.cdut.edu.cn/info/1231/7640.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7641` | [教师个人简介（cist）—于真](https://cist.cdut.edu.cn/info/1231/7641.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7642` | [教师个人简介（cist）—程晗蕾](https://cist.cdut.edu.cn/info/1231/7642.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7643` | [教师个人简介（cist）—彭鹏](https://cist.cdut.edu.cn/info/1231/7643.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7644` | [教师个人简介（cist）—李瑞佳](https://cist.cdut.edu.cn/info/1231/7644.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7645` | [教师个人简介（cist）—何素兰](https://cist.cdut.edu.cn/info/1231/7645.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7646` | [教师个人简介（cist）—曾维](https://cist.cdut.edu.cn/info/1231/7646.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7665` | [教师个人简介（cist）—罗俊松](https://cist.cdut.edu.cn/info/1231/7665.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7669` | [教师个人简介（cist）—温泉](https://cist.cdut.edu.cn/info/1231/7669.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |
| [x] | `cdut:source:cistprofile-1231-7670` | [教师个人简介（cist）—王权海](https://cist.cdut.edu.cn/info/1231/7670.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7672` | [教师个人简介（cist）—刘同](https://cist.cdut.edu.cn/info/1231/7672.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7673` | [教师个人简介（cist）—林杰](https://cist.cdut.edu.cn/info/1231/7673.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7674` | [教师个人简介（cist）—涂德志](https://cist.cdut.edu.cn/info/1231/7674.htm) | 计算机与网络安全学院（示范性软件学院） |  | 1 |  |
| [x] | `cdut:source:cistprofile-1231-7709` | [教师个人简介（cist）—罗耀华](https://cist.cdut.edu.cn/info/1231/7709.htm) | 计算机与网络安全学院（示范性软件学院） |  | 0 |  |

## 教师字段冲突（35，均无可比较页面日期 → 取教师主页平台值）

| 姓名 | 字段 | 采用 | 另一值 |
|---|---|---|---|
| 王洪辉 | office | 四川省工程中心楼308室（工作室：四川省工程中心（环境楼）308室） | 网安楼 204 |
| 王洪辉 | research_areas | 地球智能探测；光纤传感技术；信息获取与处理；人工智能；仪器设备研制；分布式光纤传感及信息处理 | 人工智能、工业互联网智能感知、光纤传感 |
| 王洪辉 | title | 教授；副院长 | 教授及相当职称（正高级） |
| 朱星 | title | 二级教授；研究员（科研系列教授） | 教授及相当职称（正高级） |
| 多滨 | research_areas | 团队研究方向：无人系统智能组网与应急通信；异构无人平台跨域协同关键技术及应用；无人系统安全；工业大模型关键技术及应用 | 无人系统智能组网、无人系统安全 |
| 多滨 | title | 教授 | 教授及相当职称（正高级） |
| 吴媛媛 | cist_profile_url | https://cist.cdut.edu.cn/info/1231/7492.htm | https://cist.cdut.edu.cn/info/1118/3710.htm |
| 罗耀华 | title | 副高 | 教授及相当职称（正高级） |
| 黄光鑫 | title | 教授 | 教授及相当职称（正高级） |
| 张澎 | title | 副教授 | 副教授及相当职称（副高级） |
| 唐小川 | title | 副教授 | 副教授及相当职称（副高级） |
| 唐源 | cist_profile_url | https://cist.cdut.edu.cn/info/1231/7488.htm | https://cist.cdut.edu.cn/info/1118/3709.htm |
| 单武扬 | title | 副教授 | 副教授及相当职称（副高级） |
| 王立 | title | 校聘教授、研究员（正高级） | 校聘教授／研究员（正高级） |
| 王美玲 | title | 校聘教授、研究员（正高级） | 校聘教授／研究员（正高级） |
| 李进凯 | title | 校聘教授、研究员（正高级） | 校聘教授／研究员（正高级） |
| 陈才华 | title | 校聘教授、研究员（正高级） | 校聘教授／研究员（正高级） |
| 杨丰铭 | title | 校聘教授、研究员（正高级） | 校聘教授／研究员（正高级） |
| 周让 | title | 校聘教授、研究员（正高级） | 校聘教授／研究员（正高级） |
| 胡亨琪 | title | 研究员 | 校聘教授／研究员（正高级） |
| 刘楠 | title | 校聘副教授、副研究员（副高级） | 校聘副教授／副研究员（副高级） |
| 杨锐 | title | 讲师，特聘副研究员 | 校聘副教授／副研究员（副高级） |
| 杨冬营 | title | 校聘副教授、副研究员（副高级） | 校聘副教授／副研究员（副高级） |
| 杨颖 | title | 校聘副教授、副研究员（副高级） | 校聘副教授／副研究员（副高级） |
| 肖鹏 | title | 副研究员 | 校聘副教授／副研究员（副高级） |
| 邱士林 | title | 副研究员 | 校聘副教授／副研究员（副高级） |
| 张罗致 | title | 副研究员 | 校聘副教授／副研究员（副高级） |
| 周清 | title | 校聘副教授、副研究员（副高级） | 校聘副教授／副研究员（副高级） |
| 范鹏 | title | 讲师 | 校聘副教授／副研究员（副高级） |
| 赵鹏飙 | title | 校聘副教授、副研究员（副高级） | 校聘副教授／副研究员（副高级） |
| 彭鹏 | title | 校聘副教授、副研究员（副高级） | 校聘副教授／副研究员（副高级） |
| 程晗蕾 | title | 校聘副教授、副研究员（副高级） | 校聘副教授／副研究员（副高级） |
| 孙伟恒 | college | 计算机与网络安全学院（名录/学院字段） | 计算机科学与技术学院（主页简介表述） |
| 李军 | research_areas | 软件开发与工程管理；高性能计算；人工智能；计算机应用技术；并行与高性能计算，计算机软件与理论、计算机视觉与深度学习在工程中的应用 | 高性能计算、计算机视觉、深度学习 |
| 李军 | title | 教授 | 官网个人简介补充（职称：教授；未出现于本次索引摘录） |
