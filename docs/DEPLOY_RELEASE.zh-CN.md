# 整包发布（release 布局）

`deploy/publish_release.py` + `deploy/_release.py` 取代按文件增量发布（`publish_*.py`、`update_routes.py`、`update_map_layout.py` 仍保留，旧测试仍覆盖它们，但新版本请用整包发布）。

## 包内容
- `backend/src/campuspilot/**` 整个包（含 `web_assets/`、`web_assets/v2/`、vendored Motion），去掉 `__pycache__`/`.pyc`
- `pyproject.toml`、`uv.lock`
- `data/cdut/*.json`、`data/cdut/rag/bootstrap.json`（+ `bootstrap.vectors.sqlite`，若有）
- `--bundle approved-YYYYMMDD[x]` 指定的知识快照（`snapshot.json`、`manifest.json`、`vectors.sqlite`；不含 `raw/`，不含 `rag/packages/`）
- `MANIFEST.json`：每个文件 sha256；版本号 `r-<内容哈希12位>`（同内容 = 同版本，重发为 UNCHANGED）

## 服务器布局
```
/opt/campuspilot/releases/<version>/    不可变发布树（旧版本即备份，默认保留 5 个）
/opt/campuspilot/current -> releases/<version>   原子 rename 切换
/opt/campuspilot/venv/                  共享虚拟环境（Python 3.14.7），代码经 PYTHONPATH 加载
/opt/campuspilot/deploy-log.jsonl       released / rolled_back 记录
```
安装流程：校验 manifest 与每个文件 sha256 → 解包到 `.staging` 后 rename → 切换 `current` → `systemctl restart campuspilot` → 健康检查（带公网 Host 头请求 `/`、`/api/catalog`、`/api/map-config`，最多 30 秒）→ 失败则切回上一版本并再次重启，报 `health_check_failed_rolled_back`，失败的树保留以便排查。首次运行时若 `current` 是普通目录（旧布局），先移到 `releases/legacy-<时间>` 作为回滚目标。

## 一次性准备（按顺序，root；本 PR 未执行）
1. `bash deploy/vps/01-swapfile.sh` — 1 GB swap，swappiness=10（1 GB 内存跑 uvicorn + 向量检索需要缓冲）。
2. `bash deploy/vps/02-venv-and-deps.sh`（要 sqlite-vec/numpy 加 `--vector`）— 建 `/opt/campuspilot/venv`。
3. 把 `deploy/vps/03-env.example` 中的变量合并进 `/etc/campuspilot/campuspilot.env`（0600）：phase2、agent loop on、DeepSeek（`https://api.deepseek.com` / `deepseek-flash` / key）、CF_ACCOUNT_ID/CF_API_TOKEN、AMAP 两个 key、`CAMPUSPILOT_RETRIEVAL_MODE=hybrid`、`CAMPUSPILOT_KNOWLEDGE_BUNDLE=approved-20261011b`、`CAMPUSPILOT_ASSET_VERSION=auto`。`PUBLIC_ORIGIN`、`CAMPUSPILOT_API_TOKEN` 保持现值。
4. 安装新单元：`cp deploy/campuspilot.release.service /etc/systemd/system/campuspilot.service && systemctl daemon-reload`（先别重启，第一次发布会重启）。
5. Caddy：用 `deploy/Caddyfile.release` 替换站点块，`caddy validate` 后 `systemctl reload caddy`。
6. 高德控制台把正式域名加入 JS key 白名单。

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
- 注意：整站目前有 basic_auth，Cloudflare 默认不缓存带 Authorization 的请求；要让 CDN 真正缓存静态资源，需把 `/assets/v-*` 放到 basic_auth 之外（资源无敏感内容）或在 Cloudflare 配缓存规则。是否放开请决定。
