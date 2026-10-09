# 提交版资料核验与录入

截至 2026-10-08：4 项事务、3 个部门、20 个地点候选、5 位教师，13 条业务来源。
本地 14 个地点已添加高德 GCJ02 建筑坐标候选，6 个仍无坐标；全部 `needs_review`，
可导航点位仍为 0。坐标依据保存在各地点的 `position`，与 13 条校园业务来源分别记录。
详见 [地图候选核对清单](MAP_CANDIDATE_REVIEW.zh-CN.md)。用户已于 10 月 8 日部署该快照，
更新助手核对完整 API 记录和网页字节；外部工具抽验与本地快照一致。

## 两个核心场景

补办独立于挂失，依据学生版第四版指南正文第 27 页（PDF 第 30 页）。
流程是自助设备选择补卡、选择服务区、开始并按设备提示操作。
该指南的余额大于 20 元不能解释为补卡工本费。当前机器、适用卡种、费用与开放时间未知。
[2026 年寒假通知](https://wxc.cdut.edu.cn/info/1006/3954.htm)列出香樟、珙桐、银杏自助区，
仅作为查找设备的线索；没有把该名单或 2023 年的学生卡分区关联为当前办理地点。

首批教师：王洪辉、蔡彪、汤影、姚光乐、胡艳梅，均来自学院官方公开页面。
[王洪辉简介](https://cist.cdut.edu.cn/info/1231/7607.htm)列出“网安楼 204 室”。
这是办公室文本线索；页面未明确本记录当前的成都/宜宾归属，不根据网页页脚推断校区。
其余四位页面没有收录可用办公室字段，保留 null。
网安楼名称来自学院招生页面；普通地点名称来自
[学校平面图](https://www.cdut.edu.cn/files/mapcl.pdf)，版本与当前变化待复核。
部分页面直连失败，来源明确使用 search_index；不宣称自动实时查看官网。

10 月 8 日重新下载并查看指南封面，仍是第四版、2024 年 8 月；补卡章节为正文第 27 页
（PDF 第 30 页）。学校平面图可直接下载，版本日期不明确。学院楼在校图上标为 22 号，
不能据此推定它就是办公室文本中的网安楼。2024 年后勤通知将网安楼称为“原附中”，
只提供历史别名线索；高德“网安楼”查询实际返回学院 POI，因此没有录入网安楼坐标，
也没有修改教师的校区、办公室或 `place_id`。

## 需补充的事实

| 优先级 | 需核对 | 记录位置 |
| --- | --- | --- |
| 最高 | 当前学生卡补办设备、所在建筑/入口、支持卡种、现行操作 | replacement 的步骤、条件、关联地点 |
| 最高 | 王洪辉当前办公室及校区，与网安楼建筑对应关系 | teachers.json 的 campus/office/place_id |
| 最高 | 两个核心场景对应建筑的高德 GCJ02 坐标及点位依据 | places.json 的 position |
| 次要 | 另外 2 位当前办公室与校区 | 老师记录，保留姓名原样 |
| 次要 | 普通地点现名、分类、坐标 | 可以减少候选数，优先核心场景 |

场景最少需 1 位当前办公室完成关联与定位；目标为 3 位。办公室不代表老师在场或承诺接待。
不把院系名称、学校总地址或一次会议地点当成教师常驻办公室。

## 录入规则

对官方业务资料，更新 sources.json 中的 URL、发行方、适用范围、检索日期及限制，
为老师新增 campus/office/place_id 或步骤关联字段添加 field_evidence，避免挂靠无关来源。
人工复核通过后可在 SourceEvidence 记录 verified、verified_at、reviewer；只有负责人可批准，
不能由脚本根据 HTTP 200 或模型输出自动升级。目录记录继续保留 needs_review。
人工现场补充不能冒充官网原文，需要在备注说明核对方式、日期和范围；
涉及没有官方依据的新事实时先补齐对应的人工证据契约再入正式业务字段。

坐标单独填写 MapPosition：longitude/latitude（数值）、coordinate_system、source_kind、
credential-free HTTPS source_url、retrieved_at、verification_status 和 note。
confirmed 必须有 confirmed_at 和 reviewer；需要负责人确认点位对应的建筑，不能只确认
地图搜到同名结果。WGS84 不直接用于高德，未核对点无导航按钮。不要将含 API key 的请求 URL
作为公开坐标依据。楼层与房号只写老师办公室文本，地图点代表建筑。

老师与关联地点必须有一致、明确的 campus；缺少办公室或跨校区关联会被加载校验拒绝。
事务步骤的 place_ids 只能使用地点目录中已存在的 ID。不要把一卡通中心名称直接当作补卡窗口。

变更后先在候选目录核对 JSON，再执行以下完整快照校验：

```powershell
.venv\Scripts\python.exe -c "from pathlib import Path; from campuspilot.directory.repository import DirectoryRepository; DirectoryRepository.load(Path('data/cdut')); print('snapshot valid')"
```

校验成功只说明契约与引用有效，不代表学校事实准确。人工核验完成后再运行核心场景测试。
不要重新执行 build_submission_inventory.py 覆盖人工修订；脚本会拒绝覆盖现有地点/教师文件。
