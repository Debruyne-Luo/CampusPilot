# 官方栏目离线发现

`scripts/official_discovery.py` 读取人工选定、由用户保存的公开栏目 HTML，提取源中实际存在的
详情页 `href` 和分页链接。它不打开浏览器、不连接网站、不执行页面脚本，也不采纳栏目标题为
制度事实。现有 `import_browser_exports.py` 仍负责已保存的砚湖易办指南 iframe 正文导入。

```powershell
python scripts/official_discovery.py `
  --root "C:\Users\21207\Desktop\cdut-pages" `
  --catalog "资助政策-成都理工大学学生处.html" `
  --catalog "round2/通知公告-计算机与网络安全学院（示范性软件学院）.html" `
  --collected-on 2026-10-14 `
  --output output/official-discovery/discovery.json
```

输出文件必须是新文件，且位于原始导出目录之外；原文件保持不变。输入路径相对 `--root`，
禁止路径穿越、符号链接和个人申请页面。源 URL 必须能从浏览器 `saved from url` 元数据核实，
URL 中的票据、令牌或账户参数会被拒绝。栏目链接中的此类地址也会被排除。

默认详情模式匹配学校网站的 `/info/.../...htm[l]` 和砚湖易办实际指南地址；不同栏目结构可明确
传入 `--detail-pattern`。工具仅以 `href` 为地址依据，不从事项编号或脚本事件猜测链接。
同一规范化 URL 合并为一条发现记录，保留每次出现的栏目、原始 `href`、链接标题和定位序号。
规范化包括主机大小写、默认端口、路径、片段、查询顺序与明确的缓存／推广参数；不会把
HTTP 擅自改成 HTTPS。

所有指定页面都会扫描，包括置顶旧文件、乱序日期和历年仍可能适用的制度。日期只保留页面中
实际出现的文本，不作为停止条件，也不推测日期缺少年份的值。`unvisited_pagination` 只列出
HTML 实际给出的、尚未提供本地捕获的分页地址；可人工继续保存这些页面，再显式加入
`--catalog`。没有保存的页、脚本生成的分页或栏目全部历史资料不会被声称已采集。

发现清单与正文包分离：发现记录的 `body_collected`、`adopted` 均为 `false`。后续应保存详情正文，
使用 `scripts/official_knowledge.py extract/compile`，核对发布部门、适用范围、日期和附件后再采纳。
