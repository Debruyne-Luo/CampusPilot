# 整包发布（release 布局）

## 2026-10-21 整合版与新机器

本轮状态、验收和切换前提见 [发布交接](qa/release-20261021.md)。用户最终选择原机
`38.244.61.184`（Ubuntu 24.04.3），沿用 `https://cdutdino.pages.dev/`。初选95.40.212.65
因Gemini和Jev地区限制退出本次发布。宣传片是本地实验材料，不进入 Git、
源码包、运行包或 Release 附件。

新知识使用 `current.json`、`last_good.json` 与 `versions/`，必须用以下新模式；旧 `--bundle`
继续可读，但不能用旧包名替代活动知识。两种模式互斥：

```powershell
python deploy/publish_release.py --knowledge-current --output output/release-current.tar.gz
python scripts/package_release.py --committed --output output/submission
```

新模式冻结两个指针及其完整 manifest 绑定内容，包括目录、向量、原件与验收材料。
损坏、缺文件、哈希不符、路径越界及符号链接都使打包失败。源码包来自 Git HEAD，最终运行包也
必须从该源码导出目录生成；开发工作区和旧的10月20日运行包不能替代最终提交。
解包后冷启动 `SnapshotStore` 与应用，核对活动版本、36项服务、前端资源及恐龙模型 SHA-256。

新机先只读盘点已有服务，再使用 `deploy/vps/04-prepare-migration.sh` 准备独立目录、用户、
1 GiB swap、官方 Caddy 与 Python 3.14.7。依赖在发布树中用锁定的 `uv.lock` 安装到共享 venv：

```bash
UV_PROJECT_ENVIRONMENT=/opt/campuspilot/venv /opt/campuspilot/tooling/uv sync \
  --project /opt/campuspilot/current --locked --no-dev --extra api --extra vector --no-install-project
```

`deploy/vps/03-env.example` 是本次显式开关模板：lexical，Jev证据/路由与DeepSeek Search开启，
Harness profile为空。真实密钥、已消耗预算和读图配置通过仓库外私有文件迁移；没有价格或凭据
时不得伪称联网/Jev启用成功，不重置原账本。应用单worker，保留systemd资源限制。

Pages代理源码在 `deploy/pages/_worker.js`，默认新源站为
`https://campuspilot.38-244-61-184.sslip.io:8443`，可用 `CAMPUSPILOT_ORIGIN` 覆盖。
它只改写真正同源浏览器的Origin，外站Origin保持原值供后端拒绝；流式正文、Cookie、状态和
缓存/安全头保留，双斜杠路径不能改变目标主机。后端 `PUBLIC_ORIGIN` 与源站HTTPS地址一致。
代理配置不授予模型权限，不把网页线索自动写入知识库。

原机的80/443已有服务，使用`deploy/Caddyfile.shared`与独立`campuspilot-gateway`。
`CAMPUSPILOT_DOMAIN`不带端口，`CAMPUSPILOT_BIND_ADDRESS=38.244.61.184`；应用的
`PUBLIC_ORIGIN`包含8443。服务单元沿用`deploy/campuspilot-gateway.service`的隔离限制，
采用APT安装时将ExecStart中的旧二进制路径替换为`/usr/bin/caddy`。Caddy发行包的默认
`caddy.service`在安装前保持masked，避免占用已有nginx的80。

复制`deploy/nginx.campuspilot-acme.conf.example`并替换主机名，只将本主机名的ACME路径
转发到127.0.0.1:18880；nginx语法检查成功后reload。Caddy在公网IP:8443提供HTTPS，
不占用原127.0.0.1:8443；HTTP挑战经已有80转发，不使用已占用的443做TLS-ALPN挑战。
共享配置保留错误状态与错误ID，删除错误日志中的request字段，避免记录请求头、查询或位置。
配置经Caddy 2.11.7、nginx语法验证与实际签证通过；其他站点保持原有配置。
依据：[内部HTTP端口](https://caddyserver.com/docs/caddyfile/options#http-port)、
[接口绑定](https://caddyserver.com/docs/caddyfile/directives/bind)、
[TLS挑战](https://caddyserver.com/docs/caddyfile/directives/tls)。

保留现有Pages项目，先创建预览部署并联调，再由Tech Lead最终审阅后提升生产部署。
旧Pages生产部署ID为 `cca0404b-2d63-4a15-b0f3-a7a204d5f17a`；它当前返回526，
只能作为配置回退记录，不能当作可用服务回滚目标。新机应保留通过检查的上一稳定应用包，
验证应用回滚后再安装候选。正式切换后观察24小时，旧环境保留至观察完成。

Cloudflare确认 `_worker.js` 支持控制台直接上传，可把 `deploy/pages/` 打成zip部署到原项目；
无需创建新的账号级令牌。[官方上传说明](https://developers.cloudflare.com/pages/get-started/direct-upload/#functions)

## 既有发布流程与事故记录

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
