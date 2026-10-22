# 学士帽恐龙接入检查

2026-10-20，工作目录 `D:/Projects/CampusPilot-integration`。基线为
`715555e` 加工作区修改；本轮未提交、推送或发布，未覆盖已有的后端、知识库和模型编辑工作。

## 模型与接入

基线已将地图引导默认模型指向 `backend/src/campuspilot/web_assets/models/graduate-dino.glb`。
它与用户当前打开的 `graduate-dinosaur-20261017/revision-03/assembly/scene.glb`
字节一致，SHA-256 为 `061a12abc7f7910f6aabe432df23e0c181c8d090880b903e36d0f95dbb53a0d6`。
模型为 19,796,800 bytes、200,160 三角面，保留已认可的身体斑点、面部和单列背鳍。

本轮补齐运行时接入问题：

- 地图 iframe 的 CSP 允许 `connect-src blob:`，使 GLTFLoader 能通过
  ImageBitmap 解码内嵌 PNG。首页、classic 页面和资源响应不增加此权限。
  修复前实际浏览器出现 CSP 拦截、模型灰白；修复后彩色贴图正常。
- 新模型前方为 +Z、后备模型为 +X，分别处理偏航，保证沿路线方向前进。
- 退出时去重释放纹理、材质、几何和解码位图；重复销毁无副作用。
- 浏览器候选预览同步使用本地 `/map-view` 响应及其 CSP，避免旧服务策略掩盖候选代码。

原引导 API、14 米显示高度、落地定位和导航交互保留。新模型是静态资产，行走反馈为整组轻微起伏；
后备旧模型仍带四足动画，不把其步态描述为新模型已有的骨骼动画。

## 验证

- 新增运行时回归先复现后备偏航和资源清理失败，再修复；新增 CSP 回归先失败再通过。
- `node --test tests/*.test.mjs tests/*.test.js`：88 项通过。
- `PYTHONPATH=backend/src .venv/Scripts/python.exe -m pytest tests/test_web.py tests/test_map_ux.py -q --capture=sys -p no:cacheprovider`：20 项通过；1 条既有 httpx 弃用提示。
- 修改的 Python 文件 Ruff 检查和格式检查通过；修改的 JS 语法检查和限定文件 Git 空白检查通过。
- `tests/browser_graduate_dino_textures.js` 在启用真实 CSP 的浏览器中解码出 8 个网格、
  6 个纹理对象，图像均为 2048×2048；控制台错误为 0。
- `tests/browser_guide_cycle.js`：默认 GLB 四次返回 200，连续三轮开始/退出、暂停/继续正常；
  无页面异常，桌面定位调用为 0；正常加载阶段控制台错误为 0。
- `tests/browser_guide_boundaries.js`：加载中结束、默认模型失败后回退 3D、两模型都失败后回退 2D、
  减少动效、1280/1920/390 像素宽度、退出路线恢复拖动均通过。
  故障注入期间的三条 503 资源错误为预期；正常恢复后无 CSP 或贴图错误。

浏览器使用隔离会话，将首页、地图 iframe 和静态资源从本地 8875 服务提供，高德底图与公开路线走现有服务。
普通浏览器访问线上域名仍看到线上版本，本次检查不代表已部署。未发送聊天问题或申请设备定位。

## 结果截图与限制

- [1440×900 最终效果](../../output/playwright/graduate-dino-20261020/final-map-1440.png)
- [1280×900](../../output/playwright/graduate-dino-20261020/map-demo-1280.png)
- [1920×900](../../output/playwright/graduate-dino-20261020/map-demo-1920.png)
- [390×900 窄屏](../../output/playwright/graduate-dino-20261020/map-demo-390.png)

窄屏为桌面 Chrome 模拟，不代表手机实机定位验收；尚未验证低端 GPU 长时间运行表现。
模型体积保持用户确认的原文件，本轮未压缩或重新生成造型。
