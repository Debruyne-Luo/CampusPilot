# 准备阶段验证记录

日期：2026-10-14（Asia/Shanghai）。对象为 [REVIEW_INPUTS.json](REVIEW_INPUTS.json) 记录的 `a38842b + WIP`，不是线上发布或历史固定整合提交。使用现有依赖，未执行安装/同步、真实模型评测、校园接口冒烟或部署。

## 本次实际结果

| 检查 | 结果与证据范围 |
| --- | --- |
| Python 全量测试 | **784 passed / 3 failed**，787 项；Windows / Python 3.14.7，仓库外临时目录；不是全量绿色 |
| Node 内建测试 | **70 passed / 0 failed**；`tests/*.test.js`、`tests/*.test.mjs` |
| Ruff | `All checks passed!`，全仓库配置范围 |
| strict mypy | `Success: no issues found in 117 source files`；pyproject 配置的 backend/src 与 tests |
| 审查输入核对 | **961 项原有文件字节一致**，HEAD/分支一致，无新增原有范围输入；审查包目录排除以避免自引用 |
| 准备工具测试 | 新增只读核对器的 7 项自动测试通过：原样、内容变化、删除、新增、前导空格文件名、提交变化、清单损坏；临时 Git 仓库独立运行 |
| 新增准备工具 Ruff | 两个 Python 文件通过 |
| 文档与差异检查 | 181 个本地链接及引用行号边界通过；`git diff --check` 退出 0 |
| Claude 安装诊断 | CLI 2.1.299，doctor 无安装问题；详情见 [环境记录](CLAUDE_ENVIRONMENT.zh-CN.md)，没有发模型请求 |
| 本地对线上存档核对 | `scripts/check_live_baseline.py` 退出 1，符合当前融合/WIP 已超出 10-13 线上存档的事实；不是本次准备引入的回归，也不证明线上实际状态 |

Python 包版本：pytest `9.1.1`、ruff `0.16.9`、mypy `2.3.1`、FastAPI `0.142.2`、Pydantic `2.13.5`、httpx `0.28.1`、pypdf `6.20.1`。Node `v24.21.0`。结果使用本机现有 `.venv`，没有另做干净环境依赖重建。

测试原始日志位于被 Git 忽略的 `output/architecture-prep/20261014/`：
[Python 最终运行](../../../output/architecture-prep/20261014/pytest-external-temp.txt)、
[Node](../../../output/architecture-prep/20261014/node.txt)、
[Ruff](../../../output/architecture-prep/20261014/ruff.txt)、
[mypy](../../../output/architecture-prep/20261014/mypy.txt)。本包可携带结果摘要；日志未纳入源码输入清单。

## 三项未关闭的发布测试

- `tests/test_release.py::test_failed_health_check_rolls_back_to_previous_release`
- `tests/test_release.py::test_legacy_directory_layout_is_migrated_and_used_for_rollback`
- `tests/test_release.py::test_old_releases_are_pruned_but_current_and_previous_kept`

三项均在 `deploy/_release.py:134` 的 `os.replace(current.switch, current)` 抛出 Windows `PermissionError: [WinError 5]`。与 [历史整合 QA](../../INTEGRATION_QA.zh-CN.md) 记录的 POSIX 目录链接切换限制一致；本次未在 Linux 独立复验，因此保留为待验项，不跳过、不修改部署代码或断言。另有一条已有 Starlette/httpx TestClient 弃用警告；未在准备阶段更换依赖。

## 执行方式与首轮条件修正

从目标仓库根目录执行最终全量命令，日志捕获在上述 output 目录：

```powershell
$taskAuditTemp = Join-Path ([System.IO.Path]::GetTempPath()) ('campuspilot-architecture-' + [guid]::NewGuid().ToString('N'))
# 新目录，不复用或清理既有目录；其位置必须在本仓库之外。
& '.\.venv\Scripts\python.exe' -X utf8 -B -m pytest -q -p no:cacheprovider --basetemp $taskAuditTemp
node --test tests/*.test.js tests/*.test.mjs
& '.\.venv\Scripts\python.exe' -m ruff check
& '.\.venv\Scripts\python.exe' -m mypy
```

首轮错误地把 pytest `--basetemp` 放在仓库内的 output 子目录，得到 **783 passed / 4 failed**。额外失败为 `test_jev_shadow.py::test_unknown_price_and_repository_credentials_fail_before_external_calls`：其正例明确要求临时凭据文件位于仓库外，仓库内路径被程序正确拒绝。读取断言及 `migration_config.secret` 后，只纠正运行目录条件，全量重跑得到最终 **784/3**；未修改实现、预期、语料或哈希。[首轮原始日志](../../../output/architecture-prep/20261014/pytest.txt) 保留以供核对。

输入核对器与其测试命令：

独立复核发现核对器会裁去 NUL 分隔 Git 输出首个路径的前导空格，可能漏报新增同名输入。先新增真实临时文件回归并确认修复前失败，再保留 NUL 输出原始字节语义，仅裁去 HEAD/branch 的行尾换行；修复后七项通过。该修正仅涉及本包预检工具。

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -B '.\docs\architecture-review\2026-10-14\test_verify_inputs.py'
& '.\.venv\Scripts\python.exe' -X utf8 -B '.\docs\architecture-review\2026-10-14\verify_inputs.py'
```

## 不由这些结果证明的事项

仓库目前没有 GitHub Actions 工作流；本地检查不等于 CI、Muse 独立 QA 或人类验收。mock/脚本化模型覆盖不证明真实回答质量、网关实际模型或额度；本次未验证线上服务、学校页面完整性、Tavily/Jev 真实服务、Linux 发布切换、真机图片与现场导航、95% 独立保留集目标。相关历史证据仍按其原始提交和限制读取。
