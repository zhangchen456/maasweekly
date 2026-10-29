# 实施状态

当前阶段：A/B，未切换现有数据 writer 和生产读取。

- 用户授权：现有服务器 PostgreSQL；明确暂不使用对象存储。
- 原文目标：服务器 `/srv/maasweekly/shared/data-store/blobs`，独立 filesystem CAS。
- 本地：PG17 隔离 socket，9项专项通过；真实192057文件影子导入与原文复制演练完成。
- 服务器：已有PG18 main。新增独立 maas_data 数据库、maasdata peer账号（4连接），blobs/backups/reports目录0700；原站点与调度未修改。
- JSONB 不支持历史NUL字符，已增加 payload_json 无损表示，并覆盖NUL/孤立surrogate恢复与数据库篡改测试。
- 备份脚本已编写，尚未安装调度；本地备份不能当作异地备份，最终生产切换前需确定异地恢复副本。
- pg_dump已恢复到空库，全部192057文件恢复到空目录；原exporter生成的七集合SHA与datasetVersion全部一致，见parity.json。
- 下一步：服务器影子数据校验；独立数据发布与网页读取尚未实施，现有 writer/发布不变。

原有成本指南/favicon/研究材料仍保留，不属于本轮新实现。
