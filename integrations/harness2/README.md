# 可选扩展：Harness² 离线研究

普通聊天无需打开此目录。提交启动器不加载实验 profile；这里保留已有适配源码与上游许可，供评委核查扩展边界。

`campus_adapter.py` 通过 JSON 子进程契约把校园任务交给同一个实际 `AgentRunner`；`patch_surface.py` 注册有限提示词编辑面。上游 Harness² 优化器本体并未随包分发，需要按 `setup.sh` 下载固定提交。优化器需要独立 Python 3.12 环境，应用使用本包 Python 3.14.7。启动优化器还需要完整仓库的实验 runner、任务集与预算网关，本精简包不承诺离线复现整套研究实验。

2026-10-20 的历史实验在冻结的 12 道保留题中：基线完成 9 题，仅策略及策略＋Jev 各完成 10 题；每题每组单次执行，不能推断普遍提升。两个校园反思为 `NO_ENTRY`，第三个优化任务因 WSL 中断而未完成；候选存在现行性核验阻断，未全局启用。该实验知识为 `kb-229ee34eba99ef34`，与本包当前知识不同。

完整历史报告保存在固定来源提交的 [docs/qa/harness-jev-20261020.md](https://github.com/Debruyne-Luo/CampusPilot/blob/15c3b9e91c9f9bde74654c1756c3158b91e363c0/docs/qa/harness-jev-20261020.md)，保留其原日期、源码身份和结论。本说明只交代可选研究模块，不把它描述为在线必经的 Agent 子系统。上游归属见 [NOTICE.md](NOTICE.md)。
