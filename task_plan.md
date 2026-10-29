# 架构改造执行计划

用户已授权按顺序完成 8 项架构改造，每项结束执行回归并归档验收资料。

## 执行顺序
- [x] AR-01 基线与合同（45/45 回归通过，验收归档）
- [x] AR-02 API 加载、索引、限流（45/45回归通过，本地验收归档；线上配置/代理链待发布）
- [x] AR-05 工作流/构建隔离（47/47、干净标准release及独立运行包通过，未推送）
- [x] AR-08 指标基础（48/48，诊断开关/真实服务/模拟告警通过，已归档）
- [x] AR-03 标准数据层与共享合同（49/49、标准release、七集合字节对账和仓库外运行通过）
- [x] AR-04 适配器与可恢复管线（50/50，最终标准包与仓库外运行通过）
- [x] AR-07 页面模型与组件（52/52、标准包、浏览器行为对账通过）
- [x] AR-06 本地存储评估/迁移演练（53/53、空目录恢复、故障与封装包通过；远端 DEFERRED）
- [x] AR-08 最终观测/容量（53/53、标准包独立运行、1x/5x/10x与诊断开关通过）

## 共同验收
每项完整回归并保存 JSON/文本报告、结果文档；失败先修复再进入下一项。未发布不可标 RELEASED。生产采用现有不可变 release/蓝绿/四入口/回退协议。

## 初始状态
基线 commit b29035eef，分支 codex/multilingual-seo；此前本会话任务文档和 README 未提交。保留这些文件。没有其他初始工作区改动。

## 错误记录
- 首次本地 HTTP benchmark：sandbox 回环 listen EPERM；改用 require_escalated 的隔离本地测试（已允许）。
- zsh 未匹配 python glob：改用 Python glob，找到 conda Python 3.12.1 及声明依赖。

其他诊断：ps 在沙箱不可用，改用会话/日志状态，不需要进程列表；benchmark 报告首次子进程因脚本更新存在混合版本字段，最终采样将在回归后重跑并锁定工具。

用户明确选择：AR-06 暂无远端桶，完成本地存储适配器、迁移/恢复演练和成本评估；不启用远端存储。

## 最终交付
八项已授权本地范围完成，各项 result/acceptance 已归档。最终候选 rl_6a78846238_6fd3cc403bf9 保留于 dist-release；未推送部署。生产代理链/实际GitHub调度/服务器预算待上线验证；AR06远端启用和Git移除DEFERRED。

## 已授权线上发布（2026-10-02）
用户同意按计划上线。整合 origin/main 6efd666e1 的今日数据；七集合新旧逐字节一致。接下来标准全量构建 → 服务器非公开候选与资源验证 → 安装候选helper/config → 正式workflow蓝绿发布 → 四入口/限流/诊断验收与回退资料归档。远端存储继续DEFERRED。

2026-10-02正式上线完成：commit8ebc6b9e4e，RID rl_8ebc6b9e4e_0da7f0c0f2bc；本地和Linux CI均53/53，蓝绿/四入口/旧游标/真实代理链/线上浏览器通过。完整证据、资源边界及回退见 docs/architecture/refactoring-2026-10/release-2026-10-02.md。远端存储DEFERRED。


# 2026-10-29 数据与代码解耦（当前执行任务）

用户已授权实施 docs/architecture/data-code-decoupling-2026-10-29.md。保留此前本地成本指南/favicon/历史材料改动。

- [x] A：冻结实际输入/公开版本与基线，确认部署资源。
- [x] B：PostgreSQL schema、幂等影子导入、独立 filesystem 与恢复，全量数据对账。
- [ ] C：独立数据版本激活/API/SSR/缓存/RSS/sitemap，固定样本与真实数据验收。
- [ ] D：正常周期验证后切换 writer，停止每日数据 Git commit 与全站构建。
- [ ] E：另行处理 Git 历史，保留原仓库恢复入口，不直接重写历史。

约束：阶段完成不等于整个目标完成；已指定现有服务器 PostgreSQL + 独立 filesystem，暂不使用对象存储。迁移保留 ID、修订、版本、游标和证据字节。

用户最新选择：现有服务器 PostgreSQL，暂不使用对象存储；原文使用服务器独立 filesystem CAS。
错误：本地 initdb sandbox shmget EPERM，改为隔离实例申请系统权限；首次 SSH 默认密钥不存在，按既有 aliyun-099 配置改用已配置密钥，不读取或打印密钥。

影子导入首次失败：历史输入含 NUL，JSONB 拒收（UntranslatableCharacter）。为这些 JSON 增加无损 text 表示并验证原始字节与结构内容，不删除或替换历史字符。专项 8 tests 已通过；真实全量重跑中。

对账工具首次读取 exporter 返回值时发生 KeyError；其注释声称 collections，但实际返回扁平七集合。已对齐实际接口并重跑，无需修改 exporter。9项PG专项、10项blob回归、6项标准输入、20项公开导出回归通过。

公网status已核验：datasetVersion ds_3622dedc、dataThrough2026-10-29、lastReloadError=null。普通sandbox DNS不可用，改用授权网络读取成功。传输首试本机旧rsync拒绝 --chmod=F600,D700，改为临时文件chmod0600后-rtp；未影响远端数据。

B/C兼容修复补充：保留有序JSON表示，canonical和7业务文件bytes均与基线一致；单次直读导出约20s，Mac进程峰值由1988MiB经可达事实精简降至1568MiB，再经有界字段名复用降至1487MiB。不能当作Linux整机预算达标；服务器导出需单独限额验证。影子代码同步遇SSH连接timeout，改用两次连接和30秒超时，不更改SSH配置。

服务器影子unpack首次被严格路径校验拒绝：本机BSD tar附带 ._sha256 AppleDouble元数据。已仅对明确的._元数据路径、regular类型、<=1MiB和AppleDouble魔数作跳过；不提取元数据，不放宽真实SHA对象校验。新增专项5项通过，重试可复用已校验对象。

2026-10-29 B 完成：现有 PostgreSQL18 专用 maas_data 已导入；原文 CAS 位于 /srv/maasweekly/shared/data-store/blobs。Linux 七业务文件逐字节一致，导出33.89s、峰值914MiB。服务器真实 pg_dump→独立空库恢复→全量192057逻辑文件/178989对象验证通过；演练数据库已清理。数据库备份与原文副本已存到本机仓库外 maasweekly-data-backups/2026-10-29，数据库SHA与服务器一致。
C 代码候选：同进程 SSR、只读查询、请求版本固定、内部 publication.json 原子发布/审计恢复、缓存、RSS/sitemap、受限周报鉴权完成本机验证。公开 v1 schema 未改变。76组完整旧链路回归、202 API tests、61数据tests、18真实SSR入口通过。独立运行包、Linux SSR/蓝绿/回退和7个正常周期仍待验收；未启用新writer、未改生产流量、未停止数据Git提交。不能标全部完成。

最新授权与执行：用户“那你切换吧”。已完成真实Linux18项、反向代理失败恢复、实际回退再切换、旧cursor和资源验证并上线SSR。7个正常周期尚未完成，本次依用户要求在实际服务器与回退验证通过后切流；正在实施writer/CI切换。Root runtime-mode保护阻止旧全站激活覆盖新服务。首次自动审批拒绝递归开放other读取权限，改为tooling root:maasdata目录750/文件640的最小组读取并成功执行，无剩余审批阻塞。
