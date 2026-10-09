# 成都校区地图候选核对清单

查询日期：2026-10-08。20 个地点名称中，14 个已添加建筑坐标候选，6 个仍没有坐标。
所有候选保持 `needs_review`，可导航点位为 0。本地搜索、列表与地图使用同一快照；
用户已于 10 月 8 日部署该增量，完整地点记录与网页字节检查通过。
这里的建筑坐标不能证明补卡设备、老师办公室或入口所在位置。

## 取得方式与可复现记录

使用高德官方 [AMap GUI CLI](https://lbs.amap.com/api/cli/map-cli/reference)，
包为 `@amap-lbs/amap-gui@1.0.3`，复用已有 Web JS API 凭据查询。
软件安装在仓库外私有工具目录，没有加入 VPS 的运行依赖。查询后已停止工具。
凭据不进入查询记录、公开 URL、源码包或截图。

以城市“成都”、建筑关键词执行有限次数 `searchPOI`，核对返回的 POI 名称、成都市/
成华区范围及现有学校平面图名称。未把学校总 POI、公交站、商店或其他学校当成建筑。
公开字段的实际返回记录保存于
[amap-candidates-20261008.json](research/amap-candidates-20261008.json)。
下面的 POI 链接是由真实返回 ID 组成的高德公开来源链接；没有宣称每个链接均已在网页
逐页打开核验。高德坐标系说明见 [基础类型](https://lbs.amap.com/api/javascript-api-v2/guide/abc/basetype)。

导入器只接受表中明确选取的 ID/名称、城市/区、GCJ02、待核验状态和校区范围。
既有非空坐标不同则停止，不自动批准导航，不修改业务关联。可在工作副本重现：

```powershell
.venv\Scripts\python.exe .\scripts\add_map_candidates.py --input .\docs\research\amap-candidates-20261008.json
```

## 14 个待核验建筑候选

坐标列顺序为经度、纬度，均为 GCJ02。目录 ID 的共同前缀为 `cdut:place:`。
负责人需核对点位是否落在对应建筑，而非只确认搜索结果同名。

| 目录名称 / ID 后缀 | 高德实际返回名称 | 坐标 | 高德 POI 来源 |
| --- | --- | --- | --- |
| 东区图书馆 / east-library | 成都理工大学二仙桥校区东区图书馆 | 104.151472, 30.676143 | [B0FFGHMVYO](https://ditu.amap.com/place/B0FFGHMVYO) |
| 行政楼 / administration | 成都理工大学-行政楼 | 104.142175, 30.674775 | [B0LRXC0YZY](https://ditu.amap.com/place/B0LRXC0YZY) |
| 财务处 / finance | 成都理工大学二仙桥校区计划财务处 | 104.143618, 30.676646 | [B0FFFDK67D](https://ditu.amap.com/place/B0FFFDK67D) |
| 校医院 / hospital | 成都理工大学二仙桥校区校医院 | 104.142586, 30.676868 | [B001C7YGLD](https://ditu.amap.com/place/B001C7YGLD) |
| 保卫处 / security | 成都理工大学保卫处 | 104.142897, 30.676368 | [B0FFIHKIYO](https://ditu.amap.com/place/B0FFIHKIYO) |
| 芙蓉食堂 / furong-dining | 成都理工大学芙蓉餐厅 | 104.140524, 30.674444 | [B0L2DH8CAW](https://ditu.amap.com/place/B0L2DH8CAW) |
| 银杏餐厅 / ginkgo-dining | 银杏餐厅(银杏路店) | 104.143811, 30.670203 | [B001C8NOJU](https://ditu.amap.com/place/B001C8NOJU) |
| 珙桐餐厅 / gongtong-dining | 成都理工大学二仙桥校区珙桐餐厅 | 104.149025, 30.672625 | [B001C8NPMY](https://ditu.amap.com/place/B001C8NPMY) |
| 香樟餐厅 / camphor-dining | 香樟餐厅 | 104.154625, 30.676964 | [B0FFGYU5VQ](https://ditu.amap.com/place/B0FFGYU5VQ) |
| 体育学院 / sports-college | 成都理工大学二仙桥校区体育学院 | 104.139965, 30.672791 | [B001C8NVRI](https://ditu.amap.com/place/B001C8NVRI) |
| 能源学院 / energy | 成都理工大学二仙桥校区能源学院 | 104.144316, 30.673864 | [B0LB2RLIG6](https://ditu.amap.com/place/B0LB2RLIG6) |
| 环境与土木工程学院 / environment-civil | 成都理工大学二仙桥校区环境与土木工程学院 | 104.143771, 30.675057 | [B001C8NZ3J](https://ditu.amap.com/place/B001C8NZ3J) |
| 外国语学院 / foreign-languages | 成都理工大学二仙桥校区外国语学院 | 104.143426, 30.675862 | [B0FFFCLM14](https://ditu.amap.com/place/B0FFFCLM14) |
| 材料与化学化工学院 / materials | 成都理工大学二仙桥校区材料与化学化工学院 | 104.143572, 30.673488 | [B0FFGC3M64](https://ditu.amap.com/place/B0FFGC3M64) |

[学校平面图](https://www.cdut.edu.cn/files/mapcl.pdf)中的对应名称提供业务侧地名线索，
图件版本日期不明确，不能独立证明 2026 年的现名、用途或入口。
文件 SHA256：`2d354d434f72657a77c8f2ec8d96f36735654e8623518ef6d636006c00a31481`。

## 暂不录入坐标的 6 个地点

| 地点 | 未录入理由 |
| --- | --- |
| 网安楼 | 搜索实际返回学院 POI B0FFJOT8OE；尚不能建立其与“原附中”建筑、办公室文本的对应关系 |
| 校园一卡通中心 | 未取得独立服务点 POI；学校总坐标不能代替补卡窗口或设备位置 |
| 地球科学学院 | 查询涉及不同 POI 与新学院名称，具体建筑范围存在歧义 |
| 东区教学楼 | 未得到教学楼群的明确 POI；不能用某一 E1A 子楼坐标替代整个记录 |
| 旅游与城乡规划学院 | 查询出现地理与规划学院，名称变更及建筑对应关系待确认 |
| 逸夫楼 | 查询命中楼内协会等条目，不能直接当作整栋楼的坐标 |

地图初始视野采用学校总 POI B001C7X6H7（104.147531, 30.675012），仅用于打开校区视野，
不写成任何事务/教师的目的地，不生成导航卡片。

## 两个核心场景仍缺的事实

校园卡补办步骤仍依据 [2024 年 8 月第四版学生指南](https://wxc.cdut.edu.cn/__local/8/1C/3C/0F34CEA8E563BE8802193833FE4_CFB792C4_36A72F.pdf)，
已重新查看封面和正文第 27 页（PDF 第 30 页）。指南中“余额大于 20 元”不是已确认工本费。
2026 年 [寒假服务通知](https://wxc.cdut.edu.cn/info/1006/3954.htm)提供香樟、珙桐、银杏
自助区线索，但其适用期已结束，不能据此确认当前设备状态和卡种。
本次没有将任何餐厅关联为补卡服务点。

[王洪辉公开简介](https://cist.cdut.edu.cn/info/1231/7607.htm)有“网安楼204室”的办公室文本。
2024 年 [后勤通知](https://news.cdut.edu.cn/info/1005/48105.htm)称网安楼为原附中，
只是历史建筑别名线索。2025 年 [招生通知](https://cist.cdut.edu.cn/info/1145/6716.htm)
列主校区及网安楼203室材料接收点；2026 年 [通知](https://cist.cdut.edu.cn/info/1136/7767.htm)
同时涉及主校区和宜宾校区，不能从材料接收点推定每位教师当前办公室。
相关官网 HTML 直连曾返回 412，采用官方页面搜索索引的部分需保留这一限制。
教师记录的校区、`place_id` 仍为空；本次没有把学院 POI 关联为办公室。

负责人确认建筑对应关系后，才能按 [资料录入规则](SUBMISSION_DATA.zh-CN.md)
记录核对人、日期与范围，再开放外部导航。当前清单供审阅，不计作核心场景定位验收。
