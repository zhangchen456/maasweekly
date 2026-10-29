# 数据存储与运行时执行状态（2026-10-29）

状态：生产网页/API 已切换 SSR 与共享数据目录，实际回退再切换通过；独立 writer 已安装，首次完整对账正在执行。工作流实现已通过 PR #12 合入 main，正式代码包发布中。每日真实采集与 Git 当前树脱离尚待最终验收，不能提前标全部完成。

只使用现有服务器 PostgreSQL 和独立 filesystem，无对象存储。账号 SQLite 保持原有独立存储。操作入口见 [独立发布手册](data-runtime-operations.md)。

## 存储与恢复

专用 PostgreSQL 库 `maas_data`、peer 用户 `maasdata`（写入）/`maasagent`（只读）。原文 CAS 在 `/srv/maasweekly/shared/data-store/blobs`，不在 Git 或应用包内；只读公开数据在 `shared/public-data/v1`。复用原 PostgreSQL18，没有重启数据库。

冻结输入 `in_72aa2a23b9fcff10f0d799dd23c06e5997d6ddceb4e5a112947f602b0c0cdd42`；公开版本 `ds_3622dedc6b79e17149d2d84bdbb04623b416445d6ef0ab1fab6a7583d48bb70e`，数据截至 2026-10-29。Linux 七业务文件逐字节一致，数据库直接导出33.894s、峰值914MiB；此数值不是完整每日更新耗时。26份既有缺失原文保持明确缺失。

服务器 dump 恢复到独立空库后，全量192057逻辑文件、178989对象校验通过（314.94s、峰值768MiB）；演练库随后清理。本机仓库外 `/Users/zhangchen/Work/maasweekly-data-backups/2026-10-29` 保存数据库、原文与清单；原 dump SHA-256 `ca70af245774f451c31ec26ed474710054683316e20c57437381dec36b31ab65`。额外357份旧日报、早期周报和执行日志已独立归档，服务器逐项校验通过并保存本机副本。持续异机备份尚无调度。

## 运行和发布行为

Astro Node middleware 与 API 同进程共享一份 Dataset，请求固定版本；PG只读池最大2连接。输入和页面材料按 input/code 保存，内部 publication.json 同时固定公开数据与页面；公开 v1 合同、ID和历史游标保持兼容。页面材料准备失败继续使用上一完整版本。

数据候选先入库和校验，再安装不可变公开文件，比较旧指针 SHA，写 prepared 审计，原子切换 publication 并完成审计；中断按精确 SHA 恢复。保留当前、7日内和至少上一版，不自动删除物理历史。周报全文继续经当前登录与权益检查，内部 SSR 路由不向匿名访问开放。

独立 writer 使用非root容器、只读代码、内存1.5GiB/CPU1限制和 Chromium sandbox。GitHub只传固定动作与凭据信封，浏览器子进程不继承LLM凭据。完整采集输入进入 writer_heads；运行日志独立入库，不混入业务 inputVersion。数据发布前生成本机数据库备份。

日更/周更工作流不再写 Git、构建 Astro 或重启网站；只改周报稿件直接导入。功能/规则修改才构建独立代码包，在 Linux 完成18项SSR验证后蓝绿切换。静态旧发布入口在 runtime-mode 下被保护，避免覆盖共享数据。

## 已验证与待验收

- 生产实际切流 → 回退旧静态站 → 再切SSR通过；旧绿槽游标在新蓝槽200。首次静态 favicon 权限失败自动回退，修复仅公开资产目录权限后通过。
- Linux18项 SSR 验收通过，含双语、条目/证据、RSS、分片 sitemap、私有周报边界和未知ID404；单次验收进程峰值约403–485MiB，现网应用RSS约247MiB。
- 本机71项PG/发布/恢复/工作流专项、203项完整API、81项价格/运行协议回归通过；价格最新版本校验已改一次索引，避免反复扫描全历史。
- 不带运行归档的干净检出构建通过：代码包181427640字节；原发布链路76组回归曾全通过。GitHub PostgreSQL集成CI通过。
- 首次服务器完整 writer 对账、正式代码发布后的真实日更、Git当前树取消跟踪仍在执行。尚未观察7个正常采集周期，不能把一次验证当作长期运行结果。

原工作区成本计算器、指南和favicon等用户改动保留在原checkout，未纳入本次迁移。Git历史不重写。
