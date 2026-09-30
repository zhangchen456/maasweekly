# T08-1A Gate B1 prerequisite probe

日期：2026-09-30（Asia/Shanghai）。范围：生产只读探针、installer 兼容性判断和 repository fix proposal。未实施补丁或任何生产 mutation。

## 结论

- pnpm prerequisite：尚未满足，但无需覆盖 Node 或安装系统 nodejs/npm。现有 Node distribution 自带可运行的 Corepack/npm，只是没有进入默认 PATH。
- PostgreSQL prerequisite：尚未安装。生产 APT 候选包的 server binary 不在默认 PATH，当前 installer preflight 不兼容。
- Repository patch：需要；先修 preflight，再经 tests 和 Reviewer 独立验收，更新 accepted SHA。
- Gate B Authorization Package：现有版本仍不可批准。可以依据本报告修订候选方案，完成 Repository Gate 后再进入正式审批。Production deployment 仍 NOT AUTHORIZED；T08-1B 未开始。

## 证据与来源

通过已有 root SSH、固定 production known_hosts、BatchMode 和 strict host-key checking 读取 `47.237.135.97`。未运行 apt update/install、corepack enable/prepare/install、service start/reload 或 installer。

本地实际 HEAD：`f699b6c07b63d90140a94062cd12e2ae9b5b1317`；读取的 `ops/install-umami.sh:84` 仍使用 `command -v postgres`。未改 installer，未改变 Gate A accepted SHA。

生产输出：

```text
node --version: v22.22.3
/usr/bin/node -> /opt/node-v22.22.3/bin/node
dpkg -S /opt/node-v22.22.3/bin/node: no path found
command -v corepack: COREPACK_NOT_FOUND
command -v npm: NPM_NOT_FOUND
command -v pnpm: PNPM_NOT_FOUND
/opt/node-v22.22.3/bin/corepack --version: 0.34.6
/opt/node-v22.22.3/bin/npm --version: 10.9.8
corepack realpath: /opt/node-v22.22.3/lib/node_modules/corepack/dist/corepack.js
npm realpath: /opt/node-v22.22.3/lib/node_modules/npm/bin/npm-cli.js
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin
/usr/local/bin: root:root 755
/opt/node-v22.22.3/bin: numeric owner 1001:1001, mode 755
postgresql Installed: (none), Candidate: 18+290ubuntu1
postgresql metapackage Depends: postgresql-18
postgresql-18 Installed: (none), Candidate: 18.6-0ubuntu0.26.04.1
postgresql-common Installed: (none), Candidate: 290ubuntu1
command -v postgres: POSTGRES_NOT_IN_PATH
command -v psql: PSQL_NOT_IN_PATH
```

APT metadata 来自服务器现有 package index，未刷新索引；候选版本可能随未来索引更新变化。

进一步将该 APT 候选 amd64 deb 下载到 Python 内存，核对 metadata 的 SHA256，再读取 archive member 名称；没有写入生产文件或执行包内脚本：

```text
package_url=http://mirrors.cloud.aliyuncs.com/ubuntu/pool/main/p/postgresql-18/postgresql-18_18.6-0ubuntu0.26.04.1_amd64.deb
sha256=0536716204dee9152dee758c252936ba41c93b7330395f8abb0c5b86558aa658
server_binary=./usr/lib/postgresql/18/bin/postgres
usr_bin_postgres_present=False
```

## pnpm 方案建议（待授权，不执行）

使用现有 Corepack 的绝对路径。其现场 `enable --help` 确认支持 `--install-directory`，默认位置取决于 Corepack 所在目录；不应依赖默认 shim 位置。

修订 Authorization Package 时明确：仅创建 pnpm shim 到 `/usr/local/bin`，固定 pnpm 版本、Corepack cache 路径及可供 `maasumami` 读取的权限；分别验证 root 和实际 build 用户的 pnpm 调用。避免只在 root cache 中准备依赖导致 service 用户无法使用。

候选 enable 形式是 `/opt/node-v22.22.3/bin/corepack enable --install-directory /usr/local/bin pnpm`，这是未来 mutation，不属于本次探针。pnpm `12.3.4` 的 registry 可用性、Node engines、签名验证及 pinned Umami packageManager 一致性仍需在后续方案中核实，本报告不宣称 pnpm 已可用。Corepack 的官方说明支持显式 shim 目录：[Corepack README](https://github.com/nodejs/corepack/blob/main/README.md)。

## PostgreSQL repository fix proposal（不实施）

把 `command -v postgres` 改为明确支持 Debian/Ubuntu package layout 的只读检查：验证已安装 server package、对应 `/usr/lib/postgresql/<major>/bin/postgres` 可执行并读取版本；如支持 PATH 安装，也验证其实际 server version。不要依靠仅安装 client/dev tools 即可能出现的 `pg_config` 判定 server 已安装；多版本时不能任取 wildcard 首项。

保留 `/usr/bin/psql` 检查。在已有 PostgreSQL active/start 阶段之后、credential/role/database mutation 之前，使用 installer 实际连接路径执行只读 SQL，确认可连接、server version 满足要求、目标 cluster/port 明确。`postgresql.service` active 本身不足以证明目标 database server 可连接。

对应验证至少覆盖：server 不在 PATH 但版本目录有效、只有 client 没有 server、版本不满足、多 cluster/版本歧义、实际连接失败时在 credential mutation 前停止。Production 不创建 workaround symlink。

## 停止点

本次只读取证完成。没有安装 package、修改 PostgreSQL、创建 DB/role/service user、部署 Umami、修改 nginx/DNS/TLS 或开始 frontend tracking。Repository patch、Reviewer 验收及新的 Authorization Package 属于下一阶段。
