# Task 06：生产发布、运行保障与 P0 首发验收

状态：待实现，可直接交给 coding agent 执行。日期：2026-09-17。

前置：Task 01–05 已完成稳定条目、价格证据、公开数据投影、REST API v1、
MCP、Agent Skill、RSS 和公开接入页面的本地实现。Task 05 当前仍是未提交工作区；
开始生产改造前必须先把 Task 05 变更整理成可审查提交并确认全量回归通过，不能
在未知工作树上构建生产 release。

本任务完成 P0-3：把静态站、公开数据、REST、MCP、Skill 和 RSS 作为同一个
可校验 release 发布到 `daily.maas.click`，建立竞争保护、健康检查和可演练回滚，
并用真实客户端完成首发验收。同时在上线前完善 Task 05 已有的 `/agent/`，使它
成为用户可以从介绍直接走到真实查询的接入落地页。只完成服务器文件上传、本地
冒烟或展示一个端点列表都不算完成。

## 1. 目标与完成后的用户体验

生产发布完成后：

1. `/agent/` 展示的 Skill、MCP、RSS、REST API 四种入口均可从公网实际使用，
   状态与真实部署一致。
2. 静态页面、RSS、REST 和 MCP 在同一 release 中读取同一个 datasetVersion；
   发布过程不会出现新页面配旧 API、旧页面配新数据或单次查询混版。
3. 每日、每周、代码发布和有权限维护者的本地发布共用同一构建／发布协议；旧
   作业不能覆盖新版本，失败发布继续服务上一有效版本。
4. 维护者可以从 release ID、Git commit 和 datasetVersion 定位线上版本，按
   固定步骤验证、回滚代码，并解释所有已经公开的稳定 ID。
5. 服务异常时静态页面和 RSS 尽量继续可用；API/MCP 返回准确错误，不回退到
   模型记忆或空的正常结果。

产品依据：[产品规划 P0-3 与非功能要求](./product-plan.md)、
[用户故事 US-12](./user-stories.md)、
[实施细化草案 F 工作包](../../research/2026-09-11-evolution-plan.md)、
[公开 API v1 合同](../../contracts/public-api-v1.md)、
[MCP v1 合同](../../contracts/mcp-v1.md)和
[RSS v1 合同](../../contracts/rss-v1.md)。

## 2. 已知生产基线与先行审计

当前文档记录的环境是：

- 主机 `aliyun-099`，公网地址 `47.237.135.97`。
- 现有静态根目录 `/var/www/maasweekly/`，由 `maasdeploy` 通过受限 SSH shell
  接收 rsync；现有工作流直接 `rsync --delete` 在线目录。
- nginx 配置位于 `/etc/nginx/sites-available/maasweekly.conf` 和共享 HTTPS
  snippet；正式域名为 `https://daily.maas.click`，旧域名行为以服务器现状为准。
- agent-api 默认监听 `127.0.0.1:8787`，生产尚无 systemd 和公网路由。
- `daily-update.yml` 当前先部署、后提交数据；三个工作流使用不同 concurrency
  group，不能共同阻止发布竞争。

这些是审计起点，不是可盲写的服务器事实。实施第一步只读检查并保存脱敏结果：

```text
nginx -T
systemctl status nginx
node --version
readlink/stat 当前站点根
磁盘剩余空间与目录属主/权限
现有证书域名与续期状态
maasdeploy forced-command / rsync 限制
最近三条 workflow 的发布顺序与 commit SHA
线上首页、status、feed、Skill 文件的当前 HTTP 状态
```

不得在仓库、日志、结果文档或 release 中写入 SSH 私钥、CURSOR_SECRET、GitHub
Secret、完整环境文件或认证 token。服务器现状与本文不同时，以只读审计为准，
在结果文档解释调整；不要为了符合任务书破坏现有可用站点。

## 3. 授权与发布边界

- 本任务允许本地代码、工作流、ops 文件、测试、release 构建和只读生产审计。
- 修改服务器 systemd、nginx、权限、受限发布入口，或首次切换公网流量前，先把
  待发布 commit、release manifest、配置 diff、冒烟结果和回滚命令准备完整，
  再取得用户对该次生产切换的明确授权。
- 已获授权的同一首发范围内，可以连续完成安装配置、候选服务、nginx 检查、
  流量切换、冒烟和必要回滚，不在每个可恢复子步骤重复询问。
- 不扩大到 DNS 迁移、新服务器、账户系统、数据库、付费 CDN、第三方监控、
  主动消息通知或 P1 产品功能。
- 不新增第二个 Agent 接入页，不照搬其他站点的品牌、文案或实现；在 Task 05
  已有 `/agent/` 上完善信息结构和真实操作流程。`/method/`、OpenAPI 和合同继续
  承担详细原理／字段说明，避免接入页变成重复文档仓库。
- 不把密钥放进 GitHub Actions 参数、命令行、systemd unit 或可读日志。稳定的
  `CURSOR_SECRET` 放在 root 管理、服务用户可读的环境文件中；服务重启后合法
  cursor 仍可验证，多实例／蓝绿槽位使用同一密钥。

## 4. 建议交付文件

最终拆分可调整，但结果文档必须记录真实路径：

```text
scripts/
  build-release.sh                  # 单一可复现构建入口
ops/
  deploy-release.sh                 # 本地/CI 共用上传与激活客户端
  verify-release.sh                 # 离线产物和线上只读检查
  rollback-release.sh               # 受控代码 release 回滚
  maas-agent@.service               # blue/green 或等价槽位服务模板
  maas-agent.env.example            # 仅变量名与安全默认值
  nginx-agent.conf                  # API/MCP/feed 路由与响应头模板
  install-production.sh             # 一次性、幂等、可审查的管理员安装
  server/
    maasweekly-deploy-shell          # rsync + 固定 activate/status 动作
    maasweekly-activate              # root 管理的校验/锁/切换 helper
  README.md                          # 运维、发布、回滚、故障排查
tests/
  test_release_build.py
  test_release_activation.py        # 临时目录/fixture，不碰真实服务
.github/workflows/
  release.yml                       # 可复用构建与部署 job/workflow
  deploy.yml
  daily-update.yml
  weekly-update.yml
docs/contracts/production-release-v1.md
docs/product/maas-daily-product-plan/task-06-result.md
```

不得把服务器实际环境文件、私钥、证书、journal 导出或包含 secret 的 nginx 全量
配置提交进仓库。

页面侧允许继续修改 Task 05 的 `agent.astro`、`CopyBlock.astro`、公开接入配置和
必要的小组件／样式；不得借此重做首页或新建开发者后台。

## 5. Release 构建合同

### 5.1 单一构建入口

`scripts/build-release.sh` 是 CI 与本地发布唯一入口。它从干净、明确的 Git commit
构建，至少执行：

1. 安装锁定依赖；校验 Node/Python 主版本。
2. 运行公开 exporter，保证最终采集、周报导入和 LLM 摘要都已写完后再投影。
3. 执行 Task 01–05 门禁、API/MCP/Skill/RSS 测试和站点生产构建。
4. 编译 agent-api；准备运行时依赖，不在生产机临时拉取未锁定包。
5. 生成一个不可变 release 目录和 manifest。

建议产物结构：

```text
release/
  site/                              # Astro dist
  data/public/v1/                    # 当前及合同要求保留的公开 release
  agent-api/
    dist/
    package.json
    package-lock.json
    node_modules/                    # 仅生产依赖，或等价可复现运行包
  metadata/
    release-manifest.json
    checksums.sha256
    versions.json
```

manifest 至少包含：release schema、release ID、Git commit、datasetVersion、
dataThrough、构建工具版本、API/MCP/Skill/RSS 合同版本、每个发布文件的相对路径、
bytes 和 SHA-256。路径必须规范化并拒绝绝对路径、`..`、符号链接逃逸、重复项和
未列文件。

release ID 由 Git commit 与 datasetVersion 等稳定输入组成；可以记录 builtAt
用于审计，但不得用构建时间生成 datasetVersion 或内容身份。同一 commit 和数据
重复构建时，业务文件及其 hash 必须一致；若运行依赖造成非确定元数据，应隔离
到不参与内容身份的审计字段并说明。

### 5.2 构建前提交边界

- 新数据必须先通过归档、引用和导出校验，再提交到仓库，之后从该提交构建并
  发布。生产环境不得先出现无法从 Git commit 恢复的新稳定 ID。
- `skip_fetch` 只使用已提交数据生成投影，不触发任何实时抓取。
- 工作区脏、HEAD 与声明 commit 不同、导出 `--check` 失败或构建产生未解释的
  tracked diff 时拒绝生产 release。
- Task 05 首发提交应包含页面、feed、API/MCP/Skill、合同、数据修复和对应结果
  文档；依赖目录、临时测试 fixture、密钥和本地日志不得混入。

## 6. 服务器目录与原子激活

具体根目录在审计后确定，必须满足以下逻辑结构：

```text
<root>/
  incoming/<release-id>/             # rsync 上传，未激活
  releases/<release-id>/             # 校验通过的不可变 release
  current -> releases/<release-id>   # 当前版本，或等价原子指针
  previous -> releases/<release-id>  # 最近可回滚代码版本
  shared/                             # root 管理环境和运行状态，不随 release 覆盖
  locks/release.lock                  # 所有发布通道共用 flock
```

要求：

- rsync 只能写 `incoming`，不能 `--delete` 当前在线 release。
- 激活 helper 只接受严格格式的 release ID 和固定动作；拒绝 shell 元字符、绝对
  路径和任意命令。它在服务器 `flock` 内完成校验和切换，因此本地与所有 CI
  workflow 之间也互斥。
- 校验 manifest 完整文件集、hash、schema、Git commit、datasetVersion、磁盘
  空间、目录权限、永久链接和 agent-api 兼容性后，才把 incoming 原子移动到
  releases。
- 相同 release 重复发布幂等成功；较旧 Git 提交默认拒绝覆盖较新线上版本。
  合法回滚必须走显式 rollback 动作并留下原因，不允许伪装成普通发布。
- release 目录激活后只读；服务账号无权改公开数据、代码、nginx 或环境 secret。
- 技术 release 至少保留当前、上一版和最近 7 个自然日；任何仍被合法 cursor
  引用的公开 datasetVersion 不得提前删除。Task 01/02 持久归档永不由本脚本清理。

## 7. Agent API 生产服务

- 使用非 root 专用服务用户；默认绑定回环地址，禁止直接监听公网。
- systemd 设置 `Restart=on-failure`、启动超时、文件描述符上限和合理硬化：只读
  系统、无新权限、私有临时目录、限制写目录和能力。配置以部署机实际 Node 22
  路径为准，不在 unit 中依赖交互 shell 或 nvm。
- 环境至少明确：`HOST=127.0.0.1`、端口、`PUBLIC_DATA_ROOT`、稳定
  `CURSOR_SECRET`、reload interval、REST/MCP 限流、MCP body limit 和允许 Origin。
- 服务只读当前候选 release 的 `data/public/v1`；不读取采集凭据、原始快照、用户
  home 或站点任意文件。
- 候选 release 先在非公开槽位／端口启动，完成 status、五类 REST/MCP 查询、
  当前与上一 datasetVersion、错误参数和热重载冒烟。失败则终止激活，当前服务
  不受影响。
- 首发可采用 blue/green systemd 实例或等价机制。切换必须让 nginx 的静态 root
  与 API upstream 同时指向同一 release；旧 worker 可以完成已开始请求，但新请求
  不得混读两个版本。
- journal 记录 release ID、datasetVersion、启动／重载状态和稳定错误 code；不
  记录 cursor secret、完整 cursor、请求正文、证据全文或用户认证信息。

## 8. nginx 合同

在启用前必须 `nginx -t`，并保留现有 HTTPS、旧域名和静态缓存行为。新增规则：

### 8.1 REST

- `/api/v1/` 只代理到回环 agent-api，保留真实方法；支持 GET/HEAD/OPTIONS，
  其他方法由应用合同拒绝。
- 传递 `ETag`、`Cache-Control`、`Vary`、`Retry-After`、`X-Request-Id` 和 CORS
  响应头；304 无响应体。错误响应不得进入共享缓存。
- nginx 层设置独立、保守的匿名限流和连接／读取超时；限流不能改变应用的
  Problem JSON 合同。若直接返回 nginx 429，需提供可识别 JSON 或明确记录边界。

### 8.2 MCP

- `/api/mcp` 只允许 POST/协议需要的方法，独立限流，最大请求体与服务端一致；
  不消耗 REST 桶。
- 所有响应 `Cache-Control: no-store`；不得进入 proxy cache。支持官方 SDK 所需
  的 content type 和连接超时，缺省 Origin 客户端可用，存在 Origin 时由应用
  白名单校验。

### 8.3 RSS、Skill 与静态站

- `/feed.xml`、`/feed/weekly.xml` 返回 `application/rss+xml; charset=utf-8`、
  `Cache-Control: public, max-age=1800`（或更长但不得短于 30 分钟）及稳定 ETag；
  `If-None-Match` 返回 304 且无 body。
- `/maas-skill/`、OpenAPI、`llms.txt` 和永久详情页从同一 release/site 提供；不得
  由旧在线目录残留文件“碰巧可用”。
- `/_astro/` 保持一年 immutable；HTML 保持 no-cache。禁止把 API/MCP 路由落回
  Astro 404 或静态文件目录。

## 9. 工作流与发布竞争

重构 `deploy.yml`、`daily-update.yml`、`weekly-update.yml`，让它们共同调用一套
release 构建／上传／激活逻辑：

1. 数据型 workflow 完成采集、归档、摘要和周报导入。
2. 运行 exporter、归档门禁和测试。
3. 提交并 push 新数据；push 失败时不发布。
4. 从刚提交的精确 SHA 构建 release；上传 incoming；调用固定激活动作。
5. 线上冒烟通过后才报告成功；失败保持／恢复上一 release。

规则：

- 不仅依赖 GitHub concurrency；服务器 `flock` 是跨 CI 与本地通道的最终互斥。
- 数据持久化 job 使用 `cancel-in-progress: false`。不得为了部署新提交取消正在写
  归档的数据作业。
- deploy workflow 的改动检测必须让 Skill 源、站点消费的 Markdown、API/MCP、
  ops、协议文件和公开配置触发部署；仅研究材料可忽略。不能依赖 GitHub 大 diff
  的前 3000 文件路径行为。
- push 触发和数据 workflow 主动发布同一 commit 时，服务器按 release ID 幂等，
  不能重复切换或生成两个版本。
- 本地有权限发布者也只调用 `build-release.sh` 与 `deploy-release.sh`，不恢复直接
  rsync 在线根目录的旁路。
- SSH host key 不使用运行时无验证的任意结果；将经管理员核验的 host key/fingerprint
  作为受控配置，并记录轮换流程。

## 10. 回滚与失败恢复

### 10.1 发布失败

- 上传中断、hash/schema/链接检查失败、候选服务起不来、`nginx -t` 失败或公网
  冒烟失败时，当前 release 继续服务；incoming 可留作诊断后清理，不切 current。
- 激活后冒烟失败，自动或按固定命令恢复 previous 的站点 root 和 API upstream，
  再验证上一版本；记录失败 release、阶段和恢复结果。

### 10.2 代码回滚与数据修正

- 代码回滚只能选择已验证能读取**当前及上一公开投影**的旧代码 release；若不兼容，
  用当前数据重新构建修复版代码，不直接切旧目录。
- 不把数据回滚到缺少已经公开 ID 的旧快照。错误数据应生成新的修正版 release，
  保留稳定 ID并通过修订／撤回解释，再向前发布。
- 回滚不删除持久归档、证据、历史 public release 或已发布 Skill 包。合法 cursor
  在保留窗口内继续工作；无法继续时返回合同规定的 `restart_query`。
- 至少在临时服务器目录完整演练一次竞争发布、候选失败和代码回滚；生产首发后
  做一次无数据丢失的受控回滚演练，并重新切回最新有效 release。

## 11. `/agent/` 上线前完善

现有 `/agent/` 已有四张接入卡、配置复制、验证问题、动态 release 示例和故障
恢复。Task 06 在真实公网入口确定后补齐“选择方式 → 完成配置 → 验证成功”的
完整路径，目标是让第一次接触项目的用户不依赖维护者解释即可接入。

### 11.1 页面信息结构

页面从上到下至少包含：

1. **首屏结论**：一句话说明 Agent 能查询什么；匿名只读、无需本站 API Key；
   展示 REST/MCP/Skill/RSS 合同版本、数据截至时间和四入口真实状态。
2. **入口导航**：Skill、MCP、RSS、REST 四个清晰锚点或切换入口；复制或打开
   操作后仍可定位当前方式。没有 JavaScript 时四段内容全部可读。
3. **方式选择说明**：用一句具体标准帮助用户选择，例如“希望自然语言自动路由
   选 Skill”“客户端支持远程 MCP 选 MCP”“阅读器订阅选 RSS”“代码集成选 API”。
4. **四段接入流程**：每段包含适用对象、真实状态、最短配置、验证动作、成功
   的样子、能力边界和排障；不只给一个 URL。
5. **共同数据边界**：观察快照、dataThrough、coverage、无结果语义、证据核验、
   修订／撤回和频率限制；详细内容链接 `/method/`。
6. **反馈与合同入口**：OpenAPI、MCP/RSS 合同、Skill manifest／源码、changelog
   和项目已有的真实反馈渠道。若尚无反馈地址，明确写“待提供”，不编造邮箱。

页面不展示虚构迁移公告、停服日期、客户端兼容、SLA、数据许可或调用能力。当前
没有旧公共 API 需要迁移，不为模仿参考页新增无事实依据的 migration 模块。

### 11.2 Skill 区块

- 首要操作使用可复制的安装提示词或安装命令；安装器仍要求显式 `--dir`，页面
  不猜用户平台目录、不使用 sudo、不宣传尚未验证的共享目录策略。
- 分成“安装 → 开新会话 → 问一句验证”三个短步骤，说明多数客户端在新会话才
  扫描 Skill。
- 只给真实验证过的客户端命令。通用安装方式与 Claude Code 可展示；Codex 在
  T18 通过前保持待验证，不放“已支持”标志。
- 提供更新、卸载和发现失败的最短排查：检查 `SKILL.md`、实际安装目录、重复
  副本、新会话、已发现 Skill 列表。不得要求用户发送 token 或本地文件。
- 成功标准是返回真实 datasetVersion、dataThrough、coverage 和站内永久链接，
  不是“下载成功”。

### 11.3 MCP 区块

- 突出唯一生产 URL、Streamable HTTP、匿名只读和无需 token。
- 提供通用 JSON 配置，以及**已经真实验证**客户端的精确配置／命令；客户端
  版本和验证日期来自 `public-access.ts`，不在页面另外维护。
- 列出五个工具名及一句话能力：changes、prices、item、evidence、weekly，让
  用户配置前知道能做什么。
- 给出一次真实工具调用问题和可观察的成功结果；说明多候选价格、数据状态、
  最大返回条数和 cursor 的基本边界。
- 排障覆盖：刷新工具列表／新会话、远程 HTTP 支持、Origin、429 Retry-After、
  服务不可用。页面不建议并发重试或用模型知识补答。

### 11.4 RSS 区块

- 分别说明变化 feed 与正式周报 feed 的内容、上限和适合场景，并提供可点击、
  可复制的 canonical URL。
- 写明 RSS 2.0、30 分钟或更慢轮询、ETag/304、GUID 稳定、撤回无法可靠召回和
  详情页权威状态。
- 不提供第三方全文，不暗示订阅等于获得商业再分发许可。
- 至少展示一个真实阅读器已经验证的名称／版本／日期；未完成前状态保持 pending。

### 11.5 REST API 区块

- 给出 status、changes、prices、item、evidence、weekly 六类入口的简短方法表，
  每项只说明用途并链接 OpenAPI，不复制全部字段表。
- 至少提供两个可直接执行的 curl：status，以及一个真实变化或价格查询。示例
  使用公开配置生成 URL，不写死会失效的 cursor、datasetVersion 或模型价格。
- 说明匿名 GET、CORS、ETag、cursor 原样回传、Problem JSON、429 退避和版本
  过期重查；不承诺未实现的增量同步、Webhook 或 SSE。

### 11.6 交互与视觉验收

- 延续现有 MaaS Daily 视觉系统；允许优化层级、锚点导航、步骤、代码块和状态
  徽标，不复制参考站点样式。
- 所有复制按钮有明确标签、成功／失败 `aria-live`、键盘焦点和手动选择回退；
  复制内容与屏幕展示一致。
- 320px、375px、768px 和桌面宽度无整页横向溢出；代码块可独立横向滚动；
  锚点不会被固定导航遮挡。
- 页面主体在无 JavaScript 时可读；开启 JavaScript 后的切换／复制不造成重复
  ID、焦点丢失或内容不可访问。
- 首屏不堆满运维信息；release ID、覆盖数量和限制放在需要做决定的位置。动态
  数据来自当前 release，客户端状态来自唯一公开配置。

## 12. 线上验收与状态翻转

上线后用公网 HTTPS 而非 localhost 完成：

1. 首页、`/agent/`、`/method/`、`/changelog/`、随机旧／新 item、evidence、价格
   和周报永久链接。
2. REST status、changes、prices、item、evidence、weekly；ETag 200→304；非法
   cursor、未知参数、方法和限流恢复。
3. MCP initialize、tools/list 和五个工具真实查询；REST/MCP 的 ID、顺序、版本、
   coverage 与数据时间一致。
4. Skill 在 Linux 临时目录安装、校验、重复更新和真实查询；不写维护者 home。
5. 两个 feed 通过标准解析器和至少一个真实 RSS 阅读器订阅；重复刷新无重复 GUID，
   缓存头、ETag 和 304 符合合同。
6. Claude Code 与 Codex 各用新会话完成“变化→条目、价格→证据、最新周报”链路。
   Codex 若仍无认证环境，必须保持阻断，不能用 curl 或 SDK 冒充。

只有对应公网入口和真实客户端全部通过后，才在 `public-access.ts` 一处将
REST/MCP/Skill/RSS 从 `pending` 翻转为 `available`，更新 changelog 的真实发布日期，
重新构建并发布最终 release。翻转后再次检查 `/agent/`，不能先展示“已上线”再
等待服务部署。

## 13. 运行保障与观察

- systemd 和 nginx 启用开机启动；重启服务器后四种入口自动恢复。
- 每次 workflow 发布后执行只读 smoke，并把 release ID、datasetVersion、HTTP
  状态、耗时和失败阶段写到 Actions summary；不保存响应全文。
- 最小运行检查覆盖：服务 active、status 数据时间、API 5xx、MCP 初始化、feed
  年龄、磁盘空间和证书续期。首版可使用现有 GitHub Actions／systemd timer，
  不为监控引入新的付费平台。
- 常用 REST 查询在部署机预热后，用 10 个并发客户端持续 5 分钟；服务端 p95
  目标 ≤1 秒，记录 p50/p95/p99、错误率、CPU 和内存。MCP 单独记录，不把模型
  生成耗时算进服务指标。
- 验证全部抓取失败时仍服务上一有效 release 并显示旧数据时间；无任何有效
  release 时 API 503，静态站不得显示空数据为正常。
- 手工榜单的 10 天新鲜度门禁保持有效；Task 06 只把维护提示纳入运行手册，
  不伪造自动化采集能力。

## 14. 开发与发布顺序

1. **冻结基线**：修正 Task 05 结果数字和 RSS 状态翻转清单；全量回归；整理
   Task 05 提交，记录 commit 与 datasetVersion。
2. **只读生产审计**：核对 nginx、目录、权限、证书、Node、受限 shell、工作流
   和线上状态；形成脱敏基线。
3. **release builder**：实现确定构建、manifest、完整文件集和离线验证测试。
4. **激活与回滚 fixture**：在临时目录完成锁、旧作业拒绝、幂等、失败保持当前、
   blue/green 切换和回滚测试。
5. **工作流收敛**：调整三条 workflow 的提交／构建／发布顺序和触发范围，使用
   同一 release 逻辑。
6. **接入页完善**：按 §11 补齐四种方式的操作、验证、边界和排障；使用 pending
   状态及候选公网 URL 构建，不提前宣称已上线。
7. **候选交付**：生成真实待发布 release、服务器配置 diff、一次性安装脚本、
   冒烟与回滚命令；此时申请生产切换授权。
8. **一次性服务器配置**：安装专用用户／目录、systemd、受限激活入口和 nginx
   配置；不开放任意 shell。
9. **首发**：上传候选、校验、非公开端口冒烟、`nginx -t`、原子切换、公网冒烟。
10. **真实客户端与 RSS**：补完 Codex、Claude Code、Skill、真实阅读器、缓存和
   性能验收；失败则保持 pending 或回滚。
11. **最终状态发布**：四入口通过后统一翻转 available，写真实 changelog 日期，
    发布最终 release。
12. **回滚演练与收尾**：演练后恢复最新有效 release，更新 README/HANDOFF、
    运维文档和 `task-06-result.md`。

## 15. 必须通过的验收

| 编号 | 场景 | 预期 |
| --- | --- | --- |
| T01 | 同一 commit/data 构建两次 | datasetVersion、业务文件和 hash 一致；manifest 无本机路径、secret 或未列文件 |
| T02 | release 路径逃逸、重复、缺文件、bytes/hash/schema 篡改 | 激活前拒绝；线上 current 不变；错误不泄露 secret |
| T03 | 工作区脏、数据未提交、HEAD 不符、export check 失败 | 生产构建拒绝，不产生可激活 release |
| T04 | 两个新旧发布并发及同 release 重试 | 服务器锁串行；旧提交不能倒灌；相同 release 幂等 |
| T05 | 上传中断、磁盘不足、候选 API 启动失败 | 当前站点/API 不变；incoming 可诊断；无半发布目录 |
| T06 | 候选服务读取当前与上一 datasetVersion | status 与六类查询可用；坏历史 release 被拒绝；合法 cursor 保持合同 |
| T07 | 原子激活时连续请求页面、RSS、REST、MCP | 每个请求只见旧或新完整版本；新请求的站点与 API 不混版 |
| T08 | systemd 重启、进程崩溃、服务器重启 | 服务自动恢复；稳定 CURSOR_SECRET 未变化；无公网监听端口 |
| T09 | nginx REST 路由、CORS、ETag、错误与限流 | GET/HEAD/OPTIONS、200→304、响应头和 Problem JSON 符合合同；错误不缓存 |
| T10 | nginx MCP 初始化、工具调用、Origin、body limit、独立限流 | 官方客户端可用；拒绝请求无副作用；POST no-store；不消耗 REST 桶 |
| T11 | 两个 RSS 公网请求及条件请求 | 正确 content type、max-age≥1800、稳定 ETag、304 无 body；GUID 无重复 |
| T12 | Skill manifest/install.sh 在 Linux 临时目录 | hash/bytes/版本正确；首装、更新、未知文件保护和真实查询通过 |
| T13 | 三 workflow 与本地授权通道发布 | 都走同一 builder/activate；数据先提交后发布；无直接 rsync 在线目录旁路 |
| T14 | deploy 触发范围 | Skill、Markdown、API/MCP、ops、合同和公开配置改动触发；纯研究材料可跳过 |
| T15 | 代码回滚与候选失败回滚 | previous 恢复；永久链接仍可解释；不删除归档；回滚记录完整 |
| T16 | 全部采集失败且有旧版／无旧版 | 有旧版时明确旧时间继续服务；无旧版时 API 503，不返回正常空数据 |
| T17 | 公网 REST 与 MCP 同条件查询 | datasetVersion、实体、顺序、coverage 和 dataThrough 一致 |
| T18 | Claude Code 与 Codex 新会话 | 均发现能力并完成变化→条目、价格→证据、正式周报；记录版本和限制 |
| T19 | 真实 RSS 阅读器订阅并重复刷新 | 两个 feed 可订阅；修订保 GUID；无重复新增；详情页为最新状态来源 |
| T20 | 部署机 10 并发、预热后持续 5 分钟 | 常用查询 p95≤1s；错误率、CPU、内存和测试数据版本有记录 |
| T21 | `/agent/` 四种方式的完整接入流程 | 每种均有选择说明、配置、验证、成功样例、边界与排障；五个 MCP 工具和六类 REST 入口准确 |
| T22 | `/agent/` 交互、响应式与无 JS | 320/375/768/桌面无页面溢出；复制和锚点键盘可用；无 JS 内容完整；无重复 ID 或焦点丢失 |
| T23 | 四入口状态翻转后的 `/agent/` | 仅真实通过入口显示 available；配置和客户端版本来自唯一配置；所有复制 URL 公网可达；无待部署假成功 |
| T24 | 首次接入人工走查 | 一名未参与实现者只看页面，在 10 分钟内完成一种接入和真实查询；记录卡点，不由维护者代操作 |
| T25 | Task 01–05 全量回归及线上链接抽查 | 全绿；公开引用零悬空；静态、API、MCP、RSS、Skill 属于同一 release |

任何以下情况都是首发阻断：事实与证据断链；相同 ID 身份变化；分页丢失或混版；
重跑产生新 GUID；MCP 与 REST 不同版；失败数据显示 fresh；安装器破坏目标目录；
旧作业覆盖新 release；站点与 API/RSS 混版；回滚会丢失已公开 ID。

## 16. 结果文档与完成定义

`task-06-result.md` 至少记录：

- Task 05 基线 commit、首发和最终 release ID、Git commit、datasetVersion、
  dataThrough、部署时间和当前／previous 指针。
- 服务器目录、systemd unit、nginx 路由、端口和环境变量名称；敏感值必须脱敏。
- 三 workflow 的最终顺序、触发范围、发布锁与旧作业拒绝证据。
- T01–T25 的命令、退出码和真实 HTTP／客户端结果；公网抽样链接。
- `/agent/` 四种方式的最终信息结构、响应式／键盘／无 JS 结果，以及首次接入
  走查的用时、卡点和修复。
- 性能数据、失败发布与回滚演练、当前日志／监控入口和维护步骤。
- Claude Code、Codex、Skill、RSS 阅读器的精确版本、日期和成功链路。
- 未关闭风险、是否产生提交、是否已经发布，以及工作区是否干净。

只有 T01–T25 全部通过、四种入口真实 available、Task 04 Codex 与 Task 05 RSS
阅读器遗留关闭、回滚演练完成，才能写“Task 06 完成，P0 首发完成”。外部认证
或生产授权缺失时，可以写“生产候选已就绪”，但不能提前翻转状态或宣布 P0 完成。

## 17. 完成后汇报格式

1. 当前线上 release、Git commit、datasetVersion、dataThrough 和四入口状态。
2. release 构建、服务器目录、systemd、nginx、发布锁和 workflow 改造。
3. REST/MCP/Skill/RSS/页面的公网验收与真实客户端版本。
4. `/agent/` 页面完善内容、首次接入走查和移动／键盘／无 JS 验收。
5. T01–T25 逐项结果和全量回归数字。
6. 性能结果、故障注入、竞争发布与回滚演练。
7. 剩余风险、日常维护动作、工作区与提交／发布状态。
