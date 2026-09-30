# T08-1A Production Authorization Package：prerequisites

状态：2026-09-30 用户批准后已执行，安装与健康验证通过。此包只覆盖生产 pnpm/PostgreSQL prerequisite，不等于 Umami deployment 或 Task 08 完成。执行证据与后续轻量化调整见 `task-08-lightweight-plan-2026-09-30.md`；下文保留原授权范围与命令记录。

2026-09-30 owner 改为由当前 Agent 直接实现和验证，不再分发给 Code Agent。本次准备保留交接文档的明确 production authorization 边界，不将仓库测试通过称作独立 Reviewer PASS。

## 已实现与核验

1. `ops/lib-umami-postgres.sh` 按 `pg_lsclusters` 找到唯一 5432 cluster，检查对应 server binary；不依赖 postgres 在 PATH。启动阶段后，以只读 SQL 验证实际版本、端口和 data directory，与发现结果一致才进入 credential 状态机。
2. installer 所有管理 SQL 固定 Unix socket `/var/run/postgresql`、port 5432，关闭 psqlrc 并启用 ON_ERROR_STOP，避免环境或默认 cluster 将操作导向其他数据库。
3. systemd 显式 `next start --hostname 127.0.0.1 --port 3000`。原来 env 中 HOSTNAME 不足以控制直接调用的 Next CLI；[Next 官方 CLI 文档](https://nextjs.org/docs/app/api-reference/cli/next) 说明 hostname 参数的默认值为 0.0.0.0。
4. installer 要求 pnpm 恰为 12.3.4；修复 fresh-install dry-run 错误读取不存在的 git checkout，以及 Bash 在变量后紧接中文时的未定义变量错误。
5. 新增 prerequisite 脚本，默认 dry-run，`--execute` 才会修改生产。

真实生产探针见同目录 `task-08-1a-gate-b1-prerequisite-probe-2026-09-30.md`。补充证据：

```text
apt-get -s install postgresql postgresql-client
0 upgraded, 14 newly installed, 0 to remove and 56 not upgraded.
Corepack 0.34.6 包含 pnpm registry signature key：
SHA256:DhQ8wR5APBvFHLF/+Tc+AYvPOdTpcIDqOhxsBHRwC7U
analytics.maas.click: getent ahostsv4 无结果
```

pnpm registry metadata 已只读核实：12.3.4 存在，engines.node 为 `>=18.*`，与 Node 22 兼容；integrity 为 `sha512-lhqkH7B32joEpEHZ+OFevAyW2o73ELLrZ7+e58sGEOq9SPH9hfUc/+c4RnhfoPh8VqOocqHYk/hEZ0G1zORUVw==`。pinned Umami commit 的 package.json 要求 engines.pnpm `12.3.4`。未关闭 Corepack signature verification。

## 请求授权的唯一生产动作

验证结果：新增 prerequisite/preflight 行为测试 14 项通过；Analytics Foundation 契约测试 94 项通过；Inventory Capability 契约测试 58 项通过。既有数据归档/投影与站点各项 quick tests 通过；本地端口限制导致的 Skill/activation 测试在放宽沙箱后分别 21 项通过、45 项通过（其中 1 项 skip）。Agent API build、REST 54 项、MCP 13 项和真实数据 MCP 8 项通过。没有执行 site rebuild（本次不改前端）。Shell syntax 与 git diff whitespace 检查通过。

统一 quick runner 在运行中被新增测试行改变了文件读取位置，尾段未正常完成；不将那次进程标为 PASS。未完成的 API 段已按原 runner 命令分别执行并通过，最终 runner 文件的 `bash -n` 已通过。

主机 `47.237.135.97`，已有 root SSH。将本补丁中 prerequisite 脚本及 PostgreSQL helper 从经过核对的仓库 SHA 放入 root-owned 工作目录，核对内容哈希后执行：

```bash
bash ops/install-umami-prerequisites.sh --dry-run
bash ops/install-umami-prerequisites.sh --execute
```

脚本执行前确认 `/usr/bin/node` 仍指向 `/opt/node-v22.22.3/bin/node`，Node/Corepack 版本与探针一致，且 pnpm shim 不存在。重新执行 APT simulation，存在 upgrade/removal 时停止。

实际执行命令：

```bash
/opt/node-v22.22.3/bin/corepack install --global pnpm@12.3.4
/opt/node-v22.22.3/bin/corepack enable --install-directory /usr/local/bin pnpm
/usr/local/bin/pnpm --version
apt-get install -y \
  postgresql=18+290ubuntu1 postgresql-18=18.6-0ubuntu0.26.04.1 \
  postgresql-client=18+290ubuntu1 postgresql-client-18=18.6-0ubuntu0.26.04.1
```

随后只读验证 server binary、cluster、connection、server version 和 Node 未改变。Corepack 使用 root 默认 cache（实际 installer 由 root 执行 pnpm install/build；运行时 systemd 直接使用 Node，不依赖 pnpm）。因此不需要为 service user 准备 pnpm cache。

## 影响范围

- 写入 root-owned staging 工作目录、root Corepack cache 和 `/usr/local/bin/pnpm` shim。
- 安装上述 PostgreSQL 包与 APT dependencies；Ubuntu package maintainer scripts 可创建 `postgres` 系统用户、默认 cluster，并启动/启用 PostgreSQL 服务。这些都是本次授权范围内的 mutation，不把 apt install 当作纯文件复制。
- PostgreSQL 默认 system catalog/cluster 属于本包；不创建应用 DB `maas_analytics` 或应用 role `maas_umami`。
- 不 apt upgrade、不安装 nodejs/npm、不改变 Node symlink、不执行 Umami installer、build、migration，不创建 maasumami，不启用 Umami、不改 nginx/DNS/TLS。
- 本次预计新增 14 packages。若 package availability、dependency plan、Node distribution 或 server baseline 变化，则停止并修订包，不动态替换版本。

## 验收与失败处理

执行前后核对现有站点、Feed、Skill、REST/MCP 和受限 shell status。要求 Node 保持 v22.22.3；pnpm 12.3.4 可调用；唯一 5432 cluster 可连接、版本为 18；PostgreSQL listener 为 loopback，不开放公网；原生产功能保持正常。

若 prerequisite 安装失败，停止 Umami 后续阶段并报告真实已发生的 mutation；不自动 purge PostgreSQL、不删 cluster，不删除 DB。Corepack 下载可能已进入 root cache；shim 若已创建则保留供核验。保留 APT install logs 和 package 状态。重跑前先读取实际状态，脚本会拒绝覆盖现有 shim，不能把它当自动 repair 工具。

## 下一阶段

本包通过并执行验证后，继续准备 Umami install/build/start 的具体包；生产 available memory 约 1 GiB、无 swap，build 资源策略尚未实测，不能直接假设 build 可承受。DNS/TLS/nginx 为另一个独立包，优先不中断 nginx 的 challenge 方式。Foundation 可用后再进入 T08-1B、T08-2/3、SEO/GEO 数据层和 Dashboard。T08-9 最后执行。
