# 整包发布（release 布局）

2026-10-12 已只读核对生产使用 release 布局，当前版本为 `r-0f1805acf68e`。
完整提交、知识包和实际配置见 [线上基线](LIVE_BASELINE.zh-CN.md)。下面保留发布操作说明；
不要因为早期 PR 的“未执行”描述而在现有服务器上重复初始化。

`deploy/publish_release.py` + `deploy/_release.py` 取代按文件增量发布（`publish_*.py`、`update_routes.py`、`update_map_layout.py` 仍保留，旧测试仍覆盖它们，但新版本请用整包发布）。

## 包内容
- `backend/src/campuspilot/**` 整个包（含 `web_assets/`、`web_assets/v2/`、vendored Motion），去掉 `__pycache__`/`.pyc`
- `pyproject.toml`、`uv.lock`
- `data/cdut/*.json`、`data/cdut/rag/bootstrap.json`（+ `bootstrap.vectors.sqlite`，若有）
- `--bundle approved-YYYYMMDD[x]` 指定的知识快照（`snapshot.json`、`manifest.json`、`vectors.sqlite`，以及知识 manifest 的 `files_sha256` 明确绑定的 `raw/` 原始材料；未绑定的 `raw/` 和 `rag/packages/` 不收录）
- `MANIFEST.json`：每个文件 sha256；版本号 `r-<内容哈希12位>`（同内容 = 同版本，重发为 UNCHANGED）

打包前校验知识 manifest 必需文件的路径及 sha256；缺失、内容变化、路径越界或符号链接会使打包失败。
保持运行时对来源材料、知识快照和向量索引的完整性校验，不通过删减知识 manifest 来缩小发布包。
本地发布验证须解包后以所选 bundle 冷启动 `SnapshotStore`；发布归档的 `read_archive` 校验通过，只能说明归档字节与发布 manifest 一致。

## 服务器布局
```
/opt/campuspilot/releases/<version>/    不可变发布树（旧版本即备份，默认保留 5 个）
/opt/campuspilot/current -> releases/<version>   原子 rename 切换
/opt/campuspilot/venv/                  共享虚拟环境（Python 3.14.7），代码经 PYTHONPATH 加载
/opt/campuspilot/deploy-log.jsonl       released / rolled_back 记录
```
安装流程：校验 manifest 与每个文件 sha256 → 解包到 `.staging` 后 rename → 切换 `current` → `systemctl restart campuspilot` → 健康检查（带公网 Host 头请求 `/`、`/api/catalog`、`/api/map-config`，最多 30 秒）→ 失败则切回上一版本并再次重启，报 `health_check_failed_rolled_back`，失败的树保留以便排查。首次运行时若 `current` 是普通目录（旧布局），先移到 `releases/legacy-<时间>` 作为回滚目标。

## 一次性准备（新环境；现有服务器先核对）
1. `bash deploy/vps/01-swapfile.sh` — 1 GB swap，swappiness=10（1 GB 内存跑 uvicorn + 向量检索需要缓冲）。
2. `bash deploy/vps/02-venv-and-deps.sh`（要 sqlite-vec/numpy 加 `--vector`）— 建 `/opt/campuspilot/venv`。
3. 把 `deploy/vps/03-env.example` 中的变量合并进 `/etc/campuspilot/campuspilot.env`（0600）：phase2、agent loop on、DeepSeek（`https://api.deepseek.com` / `deepseek-flash` / key）、CF_ACCOUNT_ID/CF_API_TOKEN、AMAP 两个 key、`CAMPUSPILOT_RETRIEVAL_MODE=hybrid`、`CAMPUSPILOT_KNOWLEDGE_BUNDLE=approved-20261011b`、`CAMPUSPILOT_ASSET_VERSION=auto`。`PUBLIC_ORIGIN`、`CAMPUSPILOT_API_TOKEN` 保持现值。
4. 安装新单元：`cp deploy/campuspilot.release.service /etc/systemd/system/campuspilot.service && systemctl daemon-reload`（先别重启，第一次发布会重启）。
5. Caddy：用 `deploy/Caddyfile.release` 替换站点块，`caddy validate` 后 `systemctl reload caddy`。
6. 高德控制台把正式域名加入 JS key 白名单。

## 升级已有服务器前必须核对（2026-10-15 事故记录）

发布包只带代码，**不带 Python 依赖**。已有服务器不会自动重跑 `02-venv-and-deps.sh`，
所以凡是新增 import 的依赖，都必须先在服务器 venv 补装，否则服务起不来。

2026-10-15 发布整合版本时正是这个原因失败：新代码在
`campuspilot/app/state.py → attachments.py` 启动时 import `PIL`，而服务器 venv 建于
依赖脚本加入 `pillow` 之前，于是 `ModuleNotFoundError: No module named 'PIL'`。
发布脚本按设计自动回滚到上一版本（`restored_healthy: true`），线上未受影响。

注意 `pillow` **与图片开关无关**：`attachments.py` 在模块加载时就 import `PIL`，
即使 `CAMPUSPILOT_IMAGES=off` 也必须安装。

发布前最小核对（在服务器上执行）：

```bash
sudo /opt/campuspilot/venv/bin/python -c "import fastapi, uvicorn, httpx, pydantic, PIL; print('api deps ok')"
sudo /opt/campuspilot/venv/bin/python -c "import sqlite_vec, numpy; print('vector deps ok')"  # 使用 hybrid 检索时需要
```

缺失时按 `pyproject.toml` 的 `api` / `vector` extra 约束补装，再发布。

同一轮还发现网关配置未同步：服务器 `/opt/campuspilot/gateway/Caddyfile.release` 是旧版，
只有单一 `request_body { max_size 16KB }`，没有 `/api/attachments` 的 10MiB 例外，
导致 37KB 的图片上传返回 **413**。仓库内的 `deploy/Caddyfile.release` 已含该例外。
网关改配置后需 `caddy validate` 再 `systemctl restart campuspilot-gateway`（该单元不支持 reload）。

**不要直接照搬仓库的 `deploy/Caddyfile.release` 覆盖线上网关**：仓库版本含 `basic_auth`，
而当前线上网关没有该块（访问鉴权在 Cloudflare Pages 入口侧）。直接覆盖会引入重复认证。
线上已应用的是"仅新增附件体积例外"的最小改动，其余保持不变。

## 每次发布（本地）
```bash
uv run --extra api pytest -q && uv run mypy && uv run ruff check .
python deploy/publish_release.py --bundle approved-20261011b --output dist/release.tar.gz          # 只打包
python deploy/publish_release.py --bundle approved-20261011b --output dist/release-2.tar.gz --publish --host campuspilot-vps
```
输出 `{"status":"RELEASED","version":...,"previous":...}`；失败时 `FAILED` 并已自动回滚。手动回滚：`ln -sfn releases/<旧版本> /opt/campuspilot/current.tmp && mv -T /opt/campuspilot/current.tmp /opt/campuspilot/current && systemctl restart campuspilot`。

## CDN / 缓存
- `CAMPUSPILOT_ASSET_VERSION=auto`：v2 页面引用 `/assets/v-<web_assets 内容哈希>/...`，应用与 Caddy 都给 `public, max-age=31536000, immutable`；ES 模块相对 import 自动跟随版本前缀。新发布内容变化 → 前缀变化，无需清 CDN。
- 未加版本的 `/assets/*`（含 /classic 旧界面）`max-age=0, must-revalidate`；`/`、`/classic`、`/map-view` `no-cache`；`/api/*` `no-store`。
- 历史部署使用过整站 basic_auth。2026-10-12 已确认 Pages 入口可直接访问，具体边缘鉴权/缓存配置本次未导出；不得从旧描述推断当前入口仍要求口令。若调整 CDN，应先检查当前缓存与源站配置。
