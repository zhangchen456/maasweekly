# T08-1A Analytics Foundation

日期：2026-09-30。状态：**Gate A round 3 修复后待三次验收**。

前置：T08-0 已正式 PASS 并合入 main（commit `ea5690aa5`）。

本任务严格遵循三 Gate 模型：**Gate A（仓库实现）→ Gate B（生产执行授权）→ Gate C（生产验收）**。
本文档在 Gate A 阶段编写，只描述仓库实现与待执行配置，不含任何生产执行。

### Gate A 验收历史

- **Gate A round 1**（commit `db4fc45b9`）：**FAIL**——install-umami.sh 首次安装执行顺序错误（build 在 env 之前，prisma 无 DATABASE_URL；database 在 role 之前，OWNER role 不存在）；role exists + env missing 时静默 ALTER USER（credential recovery 语义矛盾）；tag 未 pin commit SHA；TLS/nginx 不闭环（安装 nginx -t 已知失败的 443 ssl config）。静态契约测试 28/28 通过但未发现这些问题——测试只检查"元素存在"，没验证"关键生命周期顺序"。
- **Gate A round 2**（commit `48ac32b0f`）：**FAIL**——修复了 round 1 的 8 项问题，但发现更根本的 P0 状态机问题：credential 状态靠过期快照变量（USER_EXISTS）推断，而非显式状态机；首次安装 CREATE USER 后 ALTER USER 制造中断窗口（CREATE USER 成功但 env 生成前失败 → 第二次执行状态 C 永久卡死）；--render-nginx 不是纯 nginx 操作（会重新运行整个 installer）；.next exists 判断 build 成功过弱。
- **Gate A round 3**（commit `b56121247`）：**FAIL**——修复了 round 2 的状态机问题，但 fresh install 仍不是可恢复事务（CREATE ROLE 后中断 → 状态 C 永久卡死，密码已丢失）；render-umami-nginx.sh 的 nginx -t 失败时已覆盖生产配置（invalid state）。
- **Gate A round 4**（commit `ed69efd90`）：**FAIL**——修复了 crash recovery 和 nginx rollback，但状态机遗漏状态 F（role=0 env=0 pending=1 → resume-before-role），pending state 已写入但 CREATE ROLE 前中断时错误进入 A_fresh 重新生成 credential。
- **Gate A round 5**（本次修复）：6 态完整状态机，新增状态 F（resume-before-role），核心 invariant：valid pending exists → never regenerate credential。

### Gate A round 5 修复项

**P0 修复（6 态完整状态机）：**
1. **新增状态 F**：role=0 env=0 pending=1 → resume-before-role（pending state 已写入但 CREATE ROLE 前中断 → reuse pending credential，不重新生成）
2. **6 态完整状态机**：
   - A. role=0 env=0 pending=0 → fresh install（generate credential）
   - F. role=0 env=0 pending=1 → resume-before-role（reuse pending credential）
   - E. role=1 env=0 pending=1 → resume-after-role（reuse pending credential）
   - B. role=1 env=1 → existing healthy（preserve）
   - C. role=1 env=0 pending=0 → fail closed（STOP）
   - D. role=0 env=1 → fail closed（STOP，inconsistent）
3. **核心 invariant**：valid pending exists → never regenerate credential（状态机 invariant 校验：PENDING_VALID=1 时不能进入 A_fresh）
4. **状态 F 行为**：reuse pending DB_PASS/APP_SECRET → CREATE ROLE → CREATE DATABASE → env → 删 pending

---

## 1. Architecture

```
Internet
   │
   ▼
 nginx (443, TLS)
   │
   ├── daily.maas.click        → maasweekly static site + agent-api（现有，不变）
   │
   └── analytics.maas.click    → Umami（127.0.0.1:3000）  ← T08-1A 新增
             │
             ▼
           Umami (Next.js, systemd)
             │
             ▼
           PostgreSQL (maas_analytics / maas_umami)
```

T08-1A 完成后：
- Umami service healthy（127.0.0.1:3000）
- PostgreSQL healthy
- Umami → PostgreSQL writable
- **但** maasweekly 页面尚未加载 Umami JS（属 T08-1B）
- 没有真实 browser page_view、没有 custom event

---

## 2. Version

| 项目 | 值 | 来源 |
|---|---|---|
| Umami 版本 | **v3.4.0** | GitHub release（2026-09-17 发布，非 prerelease） |
| Umami commit SHA | **ec0ff50388c264ed8ce46f00967e92f7e71476ae** | GitHub git refs/tags/v3.4.0 |
| License | MIT | GitHub LICENSE |
| 官方源 | github.com/umami-software/umami | 官方 GitHub |
| Node.js | 18.18+（生产用 Node 22，对齐 maasweekly） | README requirements |
| PostgreSQL | v12.14+ | README requirements |
| packageManager | pnpm 12.3.4 | package.json |

### Version Pinning

- 固定 tag `v3.4.0`（`git clone --branch v3.4.0 --depth 1`）
- **同时 pin 40-char commit SHA**（`ec0ff50388c264ed8ce46f00967e92f7e71476ae`）
- clone 后验证 HEAD == pinned SHA，防 upstream tag 移动
- 禁止 `latest` / `main` / `master`
- install-umami.sh 硬编码 `UMAMI_VERSION="v3.4.0"` + `UMAMI_COMMIT="ec0ff50388c264ed8ce46f00967e92f7e71476ae"`
- 已存在 UMAMI_DIR 时验证 HEAD + clean worktree，不一致 fail closed

---

## 3. Official Dependency Source

- GitHub：https://github.com/umami-software/umami
- Release v3.4.0：https://github.com/umami-software/umami/releases/tag/v3.4.0
- License：MIT

---

## 4. Deployment Model

**从源码部署**（非 Docker）：

```bash
git clone --branch v3.4.0 --depth 1 https://github.com/umami-software/umami.git
cd umami
pnpm install --frozen-lockfile
pnpm run build    # 含 prisma 自动建表
# 启动（systemd 管理）：
next start        # 经 scripts/start-env.js，读 PORT/HOSTNAME env
```

**选择 source deployment 而非 Docker 的理由：**
- maasweekly 生产服务器当前不使用 Docker（agent-api 是 Node.js + systemd）
- 复用现有 Node 22 + systemd + nginx 运维模式，不为 Umami 单独引入 Docker
- source deployment 版本管理更透明（git tag + pnpm lockfile）

---

## 5. PostgreSQL

| 项目 | 值 |
|---|---|
| Database | `maas_analytics` |
| User | `maas_umami` |
| Password | install-umami.sh 现场生成（`openssl rand -hex 24`），写入 umami.env |
| 权限 | `maas_umami` 只拥有 `maas_analytics` 的权限，不使用 superuser |

**Schema 管理：** Umami 使用 prisma，build 步骤自动建表（`pnpm run build` 含 `build:db` → prisma migrate）。升级时使用官方 `prisma migrate deploy`，不自维护 schema。

---

## 6. Secrets

### 6.1 Secret 清单

| Secret | 用途 | 生成方式 | 存储位置 |
|---|---|---|---|
| `DATABASE_URL` 中的 DB password | PostgreSQL 认证 | `openssl rand -hex 24` | `/srv/maasweekly/shared/umami.env`（0740 root:maasumami） |
| `APP_SECRET` | Umami 应用密钥 | `openssl rand -hex 32` | 同上 |

### 6.2 Secret 安全红线

- 密码/APP_SECRET **不入仓库**（仓库只有 `ops/maas-umami.env.example` 占位符）
- **不入 systemd unit**（unit 只 `EnvironmentFile` 引用 umami.env）
- **不入 nginx 配置**
- **不出现在测试 fixture**
- install-umami.sh 生成 secret 时不输出到日志、不输出到汇报

### 6.3 仓库内 secret 检查

- `ops/maas-umami.env.example`：只有占位符 `<root 生成，不入仓库>`
- `ops/install-umami.sh`：用 `openssl rand` 现场生成，无硬编码值
- 测试 `test_analytics_foundation.py` 验证 env.example 无真实 secret

### 6.4 Credential 状态机（Round 5 P0 修复——6 态完整状态机）

install-umami.sh 对 credential 状态采用显式 6 态状态机（含 pending state crash recovery），**状态检测发生在任何 mutation 之前**：

| 状态 | role | env | pending | 行为 |
|---|---|---|---|---|
| A. fresh install | 0 | 0 | 0 | generate credential + 写 pending → CREATE ROLE → CREATE DATABASE → env → 删 pending |
| F. resume-before-role | 0 | 0 | 1 | reuse pending credential → CREATE ROLE → CREATE DATABASE → env → 删 pending |
| E. resume-after-role | 1 | 0 | 1 | reuse pending credential → 补 CREATE DATABASE（若缺）→ env → 删 pending |
| B. existing healthy | 1 | 1 | - | preserve credential（不 ALTER USER，清理残留 pending state） |
| C. incomplete (no recovery) | 1 | 0 | 0 | **STOP（die），fail closed**（无 pending state 可恢复） |
| D. inconsistent | 0 | 1 | - | **STOP（die），fail closed**（inconsistent） |

**核心 invariant（Round 5 修复）：valid pending exists → never regenerate credential。**
- 状态 F（role=0 env=0 pending=1）：pending state 已写入但 CREATE ROLE 前中断 → reuse pending credential，不重新生成
- 状态机 invariant 校验：PENDING_VALID=1 时不能进入 A_fresh（会重新生成 credential）

**Pending install state：**
- 路径：`/srv/maasweekly/shared/.umami-install-state`（0600 root:root）
- 内容：`DB_PASS=<hex>` + `APP_SECRET=<hex>`
- 时机：credential 在第一次 PostgreSQL mutation 前持久化；CREATE ROLE / DB / env 完成后删除
- 安全：不入 git/log，不在输出中泄露 secret；权限/属主/内容完整性校验
- crash recovery：CREATE ROLE 前中断（状态 F）或后中断（状态 E）→ 重跑检测到 valid pending → resume

**状态 C/D 处理：**
- 状态 C（role=1 env=0 pending=0）：密码已丢失且无 pending state 可恢复。installer `die`，不自动 rotate，不提供 destructive recovery 路径。需人工诊断。
- 状态 D（role=0 env=1）：inconsistent 状态。installer `die`。需人工诊断。
- **数据默认保留。inconsistent state 只 STOP + 人工诊断，不提供 destructive recovery。**

---

## 7. systemd

### 7.1 Service 文件

`ops/maas-umami.service`（安装到 `/etc/systemd/system/maas-umami.service`）

- **User/Group**：`maasumami`（非 root，无 login shell）
- **EnvironmentFile**：`/srv/maasweekly/shared/umami.env`
- **WorkingDirectory**：`/srv/maasweekly/umami`
- **ExecStart**：`/usr/bin/node /srv/maasweekly/umami/node_modules/.bin/next start`
- **Restart**：`on-failure`，`RestartSec=2`
- **硬化**（对齐 `ops/maas-agent@.service`）：
  - `NoNewPrivileges`、`PrivateTmp`、`ProtectSystem=strict`、`ProtectHome`
  - `ReadWritePaths=/srv/maasweekly/umami`
  - `ProtectKernelTunables/Modules/ControlGroups`、`RestrictNamespaces/SUIDSGID`
  - `LockPersonality`、`LimitNOFILE=8192`
  - `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`
  - **不用 `MemoryDenyWriteExecute`**（Node/V8 JIT 需要 RWX，与 agent-api 同理）

---

## 8. Nginx

### 8.1 Endpoint 决策

**冻结方案 B：`analytics.maas.click` 独立子域名**（owner 本轮决策）。

理由：
- Umami v3.4.0 官方默认 root-path 部署，不采用 `/analytics/` subpath
- 避免为迁就当前架构增加 Umami base-path patch/rewrite
- 降低未来 Umami 版本升级风险
- 边界清晰：`daily.maas.click` = 产品站，`analytics.maas.click` = Analytics infrastructure

### 8.2 配置文件

`ops/nginx/maasweekly-umami.conf`（安装到 `/etc/nginx/conf.d/maasweekly-umami.conf`）

- 独立 server block，`server_name analytics.maas.click`
- `proxy_pass http://127.0.0.1:3000`（Umami backend 仅 localhost）
- `proxy_set_header Host / X-Real-IP / X-Forwarded-For / X-Forwarded-Proto`
- HTTP/1.1 + Upgrade（Next.js 需要）
- HTTP → HTTPS 重定向
- **不影响现有 route contract**：不含 `/api/v1/` / `/api/mcp` 等 agent-api location

### 8.3 DNS + TLS（OWNER ACTION REQUIRED，分阶段执行）

⚠️ **Gate B prerequisite（owner 必须完成，分阶段）：**

installer 不安装 nginx config（Round 3 修复：render-nginx 拆为独立脚本）。Gate B 分阶段执行：

- **Phase 1**：DNS：`analytics.maas.click → 47.237.135.97`（A 记录）
- **Phase 2**：`certbot certonly -d analytics.maas.click`（获取证书路径）
- **Phase 3**：`ops/render-umami-nginx.sh <cert-path> <key-path>`（独立脚本，只渲染 nginx config + nginx -t + reload，不触发 PostgreSQL/source/build/systemd mutation）
- **Phase 4**：`systemctl enable --now maas-umami.service`
- **Phase 5**：`curl http://127.0.0.1:3000/api/heartbeat`（验证 Umami 健康）

**render-umami-nginx.sh 职责隔离（Round 3 P1 修复）：**
- 只做 nginx 操作：sed 渲染 ssl_certificate → atomic rename → nginx -t → reload
- 不触发 PostgreSQL mutation（CREATE USER/DATABASE/ALTER USER）
- 不触发 source/build mutation（git clone/pnpm install/pnpm run build）
- 不触发 systemd mutation（systemctl enable/start/daemon-reload）
- Production Authorization Package 可准确标注 Phase 3 = nginx mutation

---

## 9. Health Checks

### 9.1 L1 Service

```bash
systemctl is-active maas-umami.service
ss -tlnp | grep 3000   # 确认 127.0.0.1:3000 监听
```

### 9.2 L2 Application

Umami v3.4.0 官方 health endpoint（docker-compose healthcheck 实证）：
```bash
curl -sf http://127.0.0.1:3000/api/heartbeat
```

### 9.3 PostgreSQL Health

```bash
systemctl is-active postgresql
sudo -u postgres psql -c "SELECT 1 FROM pg_database WHERE datname='maas_analytics'"
sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='maas_umami'"
# Umami 可写验证（不输出 password）：
sudo -u maas_umami psql -d maas_analytics -c "SELECT count(*) FROM account"
```

**健康检查不输出 DATABASE_URL / password / secret。**

---

## 10. Upgrade

未来 Umami vX → vY 升级路径：
1. 备份 PostgreSQL：`pg_dump maas_analytics > backup-$(date +%F).sql`
2. `cd /srv/maasweekly/umami && git fetch --tags && git checkout vY`
3. `pnpm install --frozen-lockfile`
4. `pnpm run build`（含 prisma 官方 migration）
5. `systemctl restart maas-umami`
6. 健康检查
7. 若失败：`git checkout vX` + `pnpm install && pnpm run build` + restart（应用回滚）
8. DB migration 兼容性评估（prisma migration 可能不可逆，需先备份）

**禁止每次升级重新初始化数据库。**

---

## 11. Rollback

`ops/rollback-umami.sh`：
- 停止并 disable `maas-umami.service`
- 备份并移除 nginx config
- `nginx -t + reload`
- **保留** umami.env、Umami 应用目录、PostgreSQL 数据
- **禁止** DROP DATABASE / dropdb / rm -rf database（除非显式 disaster recovery）

---

## 12. Gate A / Gate B / Gate C

### Gate A — Repository Implementation（当前阶段）

- 新增：`ops/maas-umami.service`、`ops/maas-umami.env.example`、`ops/nginx/maasweekly-umami.conf`、`ops/install-umami.sh`、`ops/rollback-umami.sh`、`tests/test_analytics_foundation.py`、本文档
- 修改：`scripts/run-all-tests.sh`（新增测试项）、`tests/test_skill_package.py`（telemetry guard 语义对齐重命名）
- **禁止**：生产 SSH、apt install、PostgreSQL 生产安装、生产 DB creation、Umami 生产 start、nginx production modification/reload、生产 secret generation、DNS modification、Layout.astro tracking、T08-1B

### Gate B — Production Execution Authorization

Gate A 验收通过后，准备 Production Authorization Package：
- 精确列出：commands to execute、files to install、packages to install、users/groups to create、database/user to create、ports、nginx changes、systemd changes、secret files、backup steps、validation commands、rollback commands
- 区分：READ-ONLY / MUTATING / SERVICE RELOAD / SERVICE RESTART
- **OWNER ACTION REQUIRED**：DNS + TLS 证书（Gate B prerequisite）
- Secret handling：生成随机 secret 写入 umami.env，不输出到汇报

### Gate C — Production Verification

部署后真实验证：
- Infrastructure：PostgreSQL active、Umami active、localhost port active、Umami HTTP healthy、DB connection healthy
- Exposure：Umami backend port NOT publicly exposed、only nginx public endpoint accessible
- Isolation：原有 `/`、`/changes`、`/pricing`、`/leaderboards`、`/feed.xml`、`/maas-skill/`、`/agent`、API、MCP 仍然健康
- Privacy：No analytics cookie、No frontend tracking yet、No page_view yet

**注意：** T08-1A 没有 Browser Tracking，"Umami dashboard 没有真实 page view"是正确状态，不是失败。

---

## 13. Owner Actions

| 项目 | 时机 | 说明 |
|---|---|---|
| DNS | Gate B prerequisite | `analytics.maas.click → 47.237.135.97` |
| TLS 证书 | Gate B prerequisite | `certbot certonly -d analytics.maas.click` |
| 取消注释 ssl_certificate | Gate B | `maasweekly-umami.conf` 的 ssl 行 |
| nginx -t + reload | Gate B | 证书配置后 |
| systemctl enable --now | Gate B | 启动 Umami 服务 |
| 健康验证 | Gate C | `/api/heartbeat` + PostgreSQL |

---

## 14. Telemetry Guard

### 14.1 原测试

`tests/test_skill_package.py` 的 `test_no_sudo_no_telemetry` 检查的是 **Skill install.sh**（`site/scripts/install-skill.sh`），不是全站通用 telemetry guard。Umami 引入不影响 Skill install.sh。

### 14.2 调整

- 重命名 `test_no_sudo_no_telemetry` → `test_skill_installer_no_sudo_no_telemetry`（语义对齐：明确检查对象是 Skill installer）
- 新增 `tests/test_analytics_foundation.py`：
  - `TestTelemetryGuard` 验证 Layout.astro 未引入 Umami script（T08-1A 不做前端采集）
  - 验证未经批准的 telemetry（gtag/Google Analytics/Segment/PostHog/Plausible/Matomo/Hotjar）仍被禁止
  - 验证 Skill install.sh 仍无 telemetry（不因 Umami 引入而破坏）

### 14.3 语义升级

从 "no telemetry" 升级为 "no unapproved telemetry"：
- 允许：Umami infrastructure/config（ops/install-umami.sh 等）
- 仍禁止：frontend tracking script（T08-1A 不做）、Google Analytics、gtag、Segment、PostHog、Plausible、其他未经批准 tracking

---

## 15. Failure Isolation

Umami 故障时：
- maasweekly static site continues working ✓
- agent-api continues working ✓
- feed continues working ✓
- skill continues working ✓
- API/MCP continues working ✓

Analytics 是 **non-critical dependency**：
- 不是 site startup dependency
- 不是 nginx global failure point（独立 server block，不影响主站）
- 不是 daily-update blocker（Analytics 失败不阻断核心数据服务）
- 不是 release activation blocker（Analytics 不进入 release 模型）

---

## 16. Tests

`tests/test_analytics_foundation.py` 覆盖契约检查，从"存在性检查"升级到"执行顺序契约"（Gate A round 2 核心修复）：

### 16.1 测试分类（46 项）

| 测试类 | 项数 | 覆盖 |
|---|---|---|
| `TestUmamiVersionPinned` | 7 | 版本 pin + commit SHA pin + clone 后 HEAD 验证 + 已存在目录 HEAD 验证 |
| `TestEnvExampleNoSecret` | 4 | env.example 无真实 secret + HOSTNAME=127.0.0.1 |
| `TestSystemdNonRoot` | 4 | 非 root + 不用 MemoryDenyWriteExecute + AddressFamilies |
| `TestNginxLocalhostUpstream` | 4 | localhost upstream + subdomain + 不影响 agent route contract |
| `TestTelemetryGuard` | 4 | Layout 无 Umami script + 无 unapproved telemetry + Skill installer 仍无 telemetry |
| `TestInstallerIdempotent` | 6 | 保留 env + credential recovery fail closed + 无硬编码 password + DB exists check |
| `TestRollbackNonDestructive` | 6 | 不 DROP DATABASE + 不 dropdb + 保留 env/app + 不影响主站 + 无 destructive cleanup 提示 |
| `TestExecutionOrderContract` | 8 | **P0 核心**：PostgreSQL active → role → database → env → clone → build → systemd → nginx 顺序契约 |
| `TestTlsNginxClosedLoop` | 4 | **P1 核心**：nginx 模板无注释 ssl_certificate + --render-nginx 模式 + 不安装无效 config + nginx -t 闭环 |

### 16.2 执行顺序契约测试（TestExecutionOrderContract，P0 核心修复）

Gate A round 1 FAIL 根因：静态契约测试 28/28 通过，但首次安装仍会失败——因为测试只检查"元素存在"，没验证"关键生命周期顺序"。

`TestExecutionOrderContract` 验证 install-umami.sh 中关键步骤的执行顺序：
- `test_postgresql_active_before_role_creation`：PostgreSQL active 在 role 之前
- `test_role_before_database`：role 在 CREATE DATABASE 之前（OWNER role 需已存在）
- `test_database_before_env`：database 在 umami.env 之前（DATABASE_URL 引用 database）
- `test_env_before_clone`：umami.env 在 clone 之前
- `test_clone_before_build`：clone 在 pnpm install/build 之前
- `test_env_before_build`：umami.env 在 pnpm run build 之前（prisma 自动建表需要 DATABASE_URL）
- `test_build_before_systemd`：build 在 systemd 安装之前
- `test_full_order_pipeline`：完整顺序 preflight → user → pg active → role → db → env → clone → build → systemd → nginx

### 16.3 Gate A 验证

```bash
python3 -m unittest discover -s tests -p 'test_analytics_foundation.py'   # 46 项
scripts/run-all-tests.sh   # 含 test_analytics_foundation
```
