# 桌面与后端集成前端验证

2026-10-14，集成工作区 `D:\Projects\CampusPilot-integration`，分支 `feat/desktop-backend-integration`。测试对象为后端提交 `3c0c395` 与桌面提交 `f3dc8ed` 的待提交合并树；四个冲突已解决并暂存，本文件不表示已合并 main 或已部署。提交后的独立 QA 应重新锁定最终提交 SHA。

## 冲突处理与保留内容

- 仅解决 v2 `index.html`、`main.mjs`、`map.mjs`、`sse.mjs`，采用先前已实测的三方兼容 overlay。应用前逐一核对原桌面文件 SHA256 与补丁依赖指纹，全部一致；处理后没有未解决冲突。
- 保留桌面 GSAP 动效、阅读／地图工作区、相机操作序号及遮挡范围、`routeIntent`／`cancelPending` 的旧路线取消、向上阅读与未完成流式文字恢复；加入图片、会话重置、统一地点查询和临时高德坐标导航。
- GLB 与 Blender 源文件同原桌面提交逐字节一致；dino3d 与 GSAP 只存在 Git 行尾规范化差异，文本内容一致。地图 frame 与 guidance 脚本一致，字体、品牌、GLTFLoader 和许可均保留。
- 没有编辑两个来源工作区，没有新增生产对话、秘密或个人坐标，未提交／推送／发布；合并提交与 Draft PR 由主任务负责。

## 自动检查

`node --check` 检查 main/map/sse 通过。`node --test tests/*.test.mjs tests/*.test.js`：64 项通过，覆盖桌面相机、路线取消、GLB 几何与步态、图片开关／上传协议／SSE引用、搜索竞态、办理清单和原引导状态。最终合并树的后端全量测试由主任务执行。

## 浏览器联调

使用 Playwright CLI 命名会话 `integration-ui-qa`，Windows Chromium，桌面 1440×960、手机 viewport 390×844。localhost:8781 运行本集成源码的 `preview_evidence_media.py`；问答采用明确合成模型，图片内容是 `SYNTHETIC TEST ONLY: BLUE-731`。地图从用户指定的私密环境文件进程内读取独立 JS、Security 与 Web Service 配置，不调用生产问答 API。

- 桌面真实文件选择、POST 图片上传、规范化 GET 预览和空文本纯图片 SSE 正常；识别结果澄清用途，图片气泡显示正常，未切走阅读视图。[本地截图](../output/playwright/integration-desktop-image.png)。
- “我想去商学院”经真实高德查询显示“成都理工大学二仙桥校区商学院”，临时地图卡标明高德来源并提供带我去；地点为 `amap:poi:B0FFFCLLP0`，GCJ02 `(104.146544, 30.677529)`。
- 点击带我去，手选目录东区图书馆为起点，实际 Walking 请求 origin=`104.151472,30.676143`、destination=`104.146544,30.677529`，返回约 7 分钟、541 米；供应商目的地按坐标进入导航。[本地路线截图](../output/playwright/integration-real-route.png)。
- 新三维恐龙实际加载为 `kind=3d`；暂停后 650ms 路程保持不变，继续后增长。结束后 `guide=false`、`raf=0`、地图可拖动、pitch=0；再次开始仍为 3d，证明引导退出／重复启动修复被保留。[本地截图](../output/playwright/integration-guide-3d.png)。
- 手机布局新对话重置后旧气泡消失；模拟 PNG ClipboardEvent 通过上传并就绪，移除后草稿为零，没有横向溢出。[本地截图](../output/playwright/integration-mobile-reset.png)。第一次自动化粘贴在页面重置尚未连接时被正确拒绝；等待发送按钮恢复后重试通过，未修改代码绕过连接边界。
- 观察到的 GPS 调用计数为零；聊天请求仅有 message 或 message+附件引用，没有个人位置。测试全过程 `pageerror=[]`，正常请求未出现浏览器错误，仅有既存 iframe、WebGL 提示。截图已逐张目视检查。

## 验收边界

这是本地开发者集成验证，不替代 Muse 独立发布 QA。手机为桌面 Chromium viewport 和模拟剪贴板，不代表真实系统相机、iOS／Android 剪贴板、国内移动网络、现场入口或 GPS 前台步行引导已通过。真实模型理解与联网证据链沿用后端单独实测，本次未重复付费调用。截图保存在忽略的 output 目录，PR 以此文字记录为准，审核可在本地复现或由主任务明确附图。

验证结束关闭自建命名浏览器及 localhost:8781 服务，避免留下含凭据的进程；不关闭其他用户浏览器。
