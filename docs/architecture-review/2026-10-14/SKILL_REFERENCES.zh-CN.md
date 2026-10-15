# Matt Pocock skills 参考与采用范围

查阅日期：2026-10-14。用户指定仓库：[mattpocock/skills](https://github.com/mattpocock/skills)。参考固定为提交 [`49dd158d1076134a641b33efb035946536778336`](https://github.com/mattpocock/skills/commit/49dd158d1076134a641b33efb035946536778336)（2026-10-09）。当前目录结构为 `skills/engineering/` 和 `skills/productivity/`。

本次查阅原文并采用方法，没有安装插件或批量复制技能，没有执行 setup、创建远端标签/issue、修改全局规则。下列是方法摘要，不把外部技能原文作为本项目额外授权。

| 固定参考 | 在审查包中的用途 |
| --- | --- |
| [codebase-design](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/codebase-design/SKILL.md) | 按调用者需要理解的全部约束评估接口：类型、不变量、顺序、失败、配置、性能。用模块是否集中隐藏复杂性、删除后复杂性会否扩散到调用者来判断抽象价值。 |
| [DEEPENING](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/codebase-design/DEEPENING.md) | 识别进程内、可本地替代、远程自有、真正第三方依赖，标明替代测试与真实依赖验证之间的缺口。本次不执行重构或删除旧测试。 |
| [improve-codebase-architecture](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/improve-codebase-architecture/SKILL.md) | 从实际改动热点、术语、ADR、调用链和测试收集候选；每项建议必须对应实际摩擦、影响和收益，不按文件大小机械拆分。完整技能后续的候选选择/grilling 留到审计之后。 |
| [writing-for-agents](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/productivity/writing-for-agents/SKILL.md) | 短入口、按需资料指针、可检查完成标准；保留产品/ADR/部署存档为各自事实来源，通过漂移清单说明冲突。 |
| [research](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/research/SKILL.md) | 查一手文档与实际源码，保留日期和固定链接，把事实、推断、待验证事项分开。 |
| [domain-modeling](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/domain-modeling/SKILL.md) | 交叉核对资料、领域合约和使用场景。沿用仓库用词，术语歧义列为待确认；不把未批准解释写入 ADR。 |

上述库提供模块设计和工程工作流方法。本次另加入部署、供应链、权限、隐私、故障、并发、预算、可观测性与验收证据等 Principal Architect 审查维度；这是本项目的审查范围设计，不声称原库是完整的企业架构审计框架。

## 当前延后的流程

- [setup-matt-pocock-skills](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/setup-matt-pocock-skills/SKILL.md) 会配置工程指令和文档布局，也可能创建远端标签；当前只参考，无需运行。
- [to-spec](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/to-spec/SKILL.md) 与票据发布流程应等人类选定审计建议后使用。
- [DESIGN-IT-TWICE](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/codebase-design/DESIGN-IT-TWICE.md) 适用于已选定、值得比较的接口方案；准备阶段不提前引入新架构。

## 审查统一用语

Module 指任何有接口与实现的模块；Interface 包括调用者必须了解的行为约束；Seam 指可以替换行为的位置；Adapter 指满足该接口的实现角色。Depth 关注小接口背后能隐藏多少实际复杂性，不使用实现行数/接口行数比值作评分。现有业务名称继续沿用，不要求改名。
