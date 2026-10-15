# 实际 Skill 使用记录

读取日期：2026-10-13。以下为**读取原文、人工应用规则**，没有安装到用户全局 skills 目录，也没有执行不可用的 Impeccable launcher / detector。不能把本记录理解为插件运行成功报告。

| 来源与阅读版本 | 实际采用 | 当前代码或检查证据 |
| --- | --- | --- |
| [Impeccable](https://github.com/pbakaus/impeccable)，SKILL 4.5.2；tree `245ad82def45831dc56a21b683c7a1ff530b06cc` | Operate 的任务主路径；craft-floor 的状态、层级与可用性；用户纠偏后以 polish 的“保留既有视觉”规则为准 | 保留 app.css 与上线首页；仅添加 desktop-enhancements.css；真实任务与异常验证 |
| [Taste Skill](https://github.com/Leonxlnx/taste-skill)，`design-taste-frontend`，源文 SHA-256 见 sources.json | 先理解用户审美；规则按上下文采用；反对重复套模板、装饰性动效 | 没有新营销首页、巨大恐龙主视觉或装饰粒子；尊重用户保留圆角与既有渐变 |
| [GSAP Skills](https://github.com/greensock/gsap-skills)，tree `aed9cfd3277740755f6bfc1155c7aa645403b760`；core / performance / timeline | 显式时长与 ease、overwrite、清理临时样式、取消旧 tween、减少动效；性能证据独立于“用了库” | desktop-motion.mjs、desktop.mjs；快速反向测试；脱敏 Chromium trace |
| [Motion 展开示例](https://github.com/motiondivision/motion/blob/main/dev/react/src/examples/Shared-layout-toggle-details.tsx) | 展开前后空间连续性，不移植 React | 引用原位展开与连续栏宽；窄屏原 Motion Mini 继续保留 |
| [MapLibre padding 示例](https://maplibre.org/maplibre-gl-js/docs/examples/offset-the-vanishing-point-using-padding/) | 遮挡和最终取景需统一计算 | 用高德自身 fit 计算四边避让，没有替换地图 SDK |

Taste 当前版本明确说其目标不是多步骤产品 UI，因此没有整套照搬。GSAP skill 的 MIT 许可证不等同于 GSAP 运行库许可证；运行库通知单独保存在 `vendor/GSAP-NOTICE.md`。

此前读过的 grilling 用于敲定范围和取舍；本阶段执行用户确认的计划，并以其后“保留上线外观”的指示覆盖原先大改视觉的决定。Playwright skill 用于真实浏览器脚本、截图、视频与验证。`app-designer`、`frontend-design`、`critiquing-visual-design` 未作为可运行的本地 skill 使用，不声称调用过它们；下面的视觉清单为人工逐屏复核。

`sources.json` 记录已读取文件的散列，便于核对版本。规则落在代码和验证记录中，不需要为了显示“配置”而增加全局配置文件。
