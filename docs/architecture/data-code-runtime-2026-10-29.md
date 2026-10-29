# 数据存储与运行时执行状态（2026-10-29）

状态：B已完成，C运行时代码本机验证；生产应用和writer未切换。只使用现有服务器PostgreSQL与独立filesystem，无对象存储。

## 已验证

服务器专用库maas_data、用户maasdata，原文CAS在 `/srv/maasweekly/shared/data-store/blobs`，不在Git或应用release内。现有PostgreSQL18未重启。原始缺失历史快照继续显式缺失。

冻结输入 in_72aa2a23b9fcff10f0d799dd23c06e5997d6ddceb4e5a112947f602b0c0cdd42；公开版本 ds_3622dedc6b79e17149d2d84bdbb04623b416445d6ef0ab1fab6a7583d48bb70e。Linux直读导出33.894s，峰值914MiB，七业务文件逐字节一致；候选未激活。这不是完整每日更新耗时。

服务器真实备份恢复到独立空库后，全量192057逻辑文件、178989对象校验通过，用时314.94s、峰值768MiB；演练库随后清理。报告在服务器独立data-store/reports目录。备份在本机仓库外 `/Users/zhangchen/Work/maasweekly-data-backups/2026-10-29`，包含85,237,896字节服务器dump、原文归档、raw manifest和checksums.json；dump SHA-256为ca70af245774f451c31ec26ed474710054683316e20c57437381dec36b31ab65。尚未设置持续异机备份调度。

## C候选行为

- 使用Astro Node middleware与API同进程，共享一份Dataset；请求使用AsyncLocalStorage固定版本，PG只读池最大2连接。
- 页面材料按input/code版本保存。内部publication.json固定公开文件和页面输入；公开v1 manifest/schema、业务文件及公开ID不改变。
- 页面输入准备失败保留上一完整版本；同dataset的翻译等页面变化也可重载。缓存按publication版本有界保存，渲染并发有上限。
- 周报全文经现有登录/当前权益检查后调用内部SSR，内部路由仅接受可信locals；公开SSR不输出原静态打包用的全文template。
- 数据候选与页面材料先提交，再安装不可变公开文件，比较旧指针SHA，写prepared审计，原子替换publication，完成审计；中断可按精确SHA恢复。保留当前、7日内和至少上一版，不自动删除物理历史。
- `build-runtime-release.sh`输出代码候选，不带业务数据，旧生产激活器不接受此格式；必须另做Linux/蓝绿/回退验收。未配置MAAS_SITE_ENTRY时继续默认静态链路。

## 验证与限制

完整原发布回归76组全通过，包含静态构建与隔离浏览器验收；API 202 tests通过；数据相关61 tests通过（内部publication修订后再跑20项PG和5项运行时针对性测试）。真实数据18项SSR验收通过，含双语、条目/证据、RSS、分片sitemap、内部周报全文隔离及未知ID404；单进程验收RSS约446MiB，仅为Mac结果。

C仍缺Linux独立SSR包运行、Nginx和蓝绿激活器适配、故障/回退演练及7个正常采集周期。D还未实施：每日writer仍写原文件并提交Git、触发旧全站构建；不能宣称已缩短现网更新时间。服务器当前只部署B影子工具，schema3；C新增schema4/5尚未安装。

后续先独立包和Linux候选验证，再接正常周期影子对账；符合C验收条件后切换writer与部署工作流。Git历史重写单独决策。原工作区成本计算器/指南/favicon等改动保留在原checkout，未纳入此分支。


## 独立运行包复核

从干净提交f6b36da945构建 `/private/tmp/maas-decoupling-20261029/runtime-package`，生产依赖和编译代码合计180,489,902字节，不包含业务data归档。以 `/private/tmp` 为cwd、明确外部PG与数据目录启动18项SSR验收全部通过；RSS462,356,480字节。包的metadata/runtime-manifest.json记录代码SHA与文件/符号链接清单；productionCompatible=false，不能交给旧激活器。此次Mac验收不代替Linux资源/权限和蓝绿回退验收。
