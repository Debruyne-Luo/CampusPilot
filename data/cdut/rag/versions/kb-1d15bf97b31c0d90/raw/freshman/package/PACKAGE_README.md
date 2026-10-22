# CampusPilot 待审核知识包 — pending-20261021-freshman

状态：**pending**。本包在 `pending-20261020` 候选快照之上追加“2026 级新生入学与熟悉校园”内容；
所有来源和片段均为待审核，没有复审人、审核日期或批准记录。

## 来源

| source_id | 页面 | 日期 | 时效 | 片段 |
|---|---|---|---|---:|
| `cdut:source:freshman-guide-2026` | [2026 新生入学须知](https://www.zs.cdut.edu.cn/info/1146/8401.htm)（页面内二维码指向 48 页电子书） | 2026-07 | current | 30 |
| `cdut:source:green-channel-2026` | [2026 级新生绿色通道](https://xsc.cdut.edu.cn/info/1025/4787.htm) | 2026-08-24 | current | 3 |
| `cdut:source:portal-home` | [砚湖易办](https://bsdt.cdut.edu.cn/EIP/nonlogin/homePage.htm) | 无 | current | 2 |
| `cdut:source:faculty-portal` | [教师个人主页平台](https://faculty.cdut.edu.cn/) | 无 | current | 1 |
| `cdut:source:admissions-charter-2026` | [2026 本科招生章程](https://www.zs.cdut.edu.cn/info/1147/8354.htm) | 无 | current | 3 |
| `cdut:source:portal-service-guide` | [砚湖易办办事指南](https://bsdt.cdut.edu.cn/EIP/nonlogin/serviceGuide/serviceGuideToPage.htm) | 无 | current | 2 |
| `cdut:source:identity-help-current` | [统一身份认证使用手册](https://wxc.cdut.edu.cn/info/1013/1560.htm) | 无 | unknown | 1 |
| `cdut:source:psych-fall-2026` | [2026 秋季心理咨询](https://xljk.cdut.edu.cn/info/1072/3678.htm) | 2026-08-28 | current | 1 |
| `cdut:source:welcome-site` | [迎新网](https://yx.cdut.edu.cn/) | 无 | current | 1 |
| `cdut:source:student-email-guide` | [学生邮箱激活方法](https://wxc.cdut.edu.cn/info/1012/3873.htm) | 2022-05-26 | unknown | 1 |

共 10 个来源、45 个片段。

## 内容

覆盖报到、线上迎新、到校交通、户口迁移、团组织关系、纸质档案、缴费方式与标准、电子票据、
生源地贷款、床上用品、军训、学院电话、奖助体系、图书馆、餐厅、一卡通、公寓门禁/用电/报修、
运动场馆、校园交通、校医院与医保、学生综合保险、安全提示、易班、团学社团、校区地址、
修业年限、入学复查、统一身份认证账号激活、安全手机更换、体检复查与疫苗、2026 秋季心理咨询、
迎新网在线报到、学生邮箱激活、入学待办时间线，以及砚湖易办和教师主页平台入口。

## 限制

- 新生入学须知是 **图片电子书 OCR**；关键数字已对照原图复核，但仍可能有识别错误，引用时
  必须带“图片识别，请以原文为准”。日期型片段（报到、床上用品、保险、绿色通道）标
  `stale=true`，检索时降权并提示可能已过期。
- 页面没有写发布日期或没有稳定正文的内容保留 `unknown`；没有补造金额、电话或地点。
- 砚湖易办只读取未登录首页和公开办事指南；没有登录、没有读取个人中心或表单。个人中心
  需要统一身份认证，不能作为公开知识来源。教师主页平台仅收录入口和用途，不新增教师个人字段。
- 没有生成向量、没有发布；本包本身不会上线。
