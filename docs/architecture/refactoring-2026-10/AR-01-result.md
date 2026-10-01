# AR-01 验收结果

日期：2026-10-01（Asia/Shanghai）。状态：**DONE**。本地基线、契约核对与完整回归完成；未执行本轮生产探针或发布。

## 输入与环境

- 输入 commit：`b29035eef9ea02f29a141b332fa5166f83ced9fd`，实现工作位于 `codex/architecture-refactoring`。
- 数据版本：`ds_6fd3cc403bf9314b2c61286faaf46e98ff27568a47b943af88c75692724a689f`；dataThrough `2026-10-01`。
- Apple M1 Max，10 核、32 GiB；Node `22.22.3`，Python `3.12.1`（conda，已存在的声明依赖）。
- 初始工作区仅包含本会话任务文档与 README 改动；本任务未修改事实、证据和公开集合。

## 交付与结论

[契约偏差与架构清单](./contract-drift.md)已保存。对齐了当前 `/api/v1/models`、REST/MCP 发布状态和 release 部署路径；早期阶段任务文档保留历史含义，未删除既有公开行为。

可复现工具：`scripts/architecture-benchmark.mjs`、`scripts/architecture-build-profile.py`、`scripts/architecture-regression.py`。测量产物为 [API 基线](./baseline.json)、[构建基线](./build-baseline.json)、[存储基线](./storage-baseline.json)。临时合成数据、临时网站输出和安装目录已自动清理。

| 数据规模 | 启动加载中位数 | 同版本重载中位数 | 重复加载后 RSS |
| --- | ---: | ---: | ---: |
| 1× | 198.7 ms | 229.4 ms | 305.2 MiB |
| 5× | 1,087.0 ms | 1,124.9 ms | 1,123.6 MiB |
| 10× | 2,490.8 ms | 2,880.1 ms | 2,179.1 MiB |

以上是开发机容量样本，RSS 不能直接作为生产单实例预算。测试包含已有元数据目录下的历史版本首次加载和 changes/prices 的完整 cursor 翻页，未出现重复或遗漏。低额度测试真实记录 200/200/429，不把限流当作成功。

| 构建阶段 | 3 轮中位耗时 |
| --- | ---: |
| 公开投影 dry-run | 15.33 s |
| 公开数据完整性校验 | 0.081 s |
| API 编译 | 1.20 s |
| 独立 outDir Astro 构建 | 35.53 s |
| 静态站 + 公开数据复制组装 | 8.65 s |
| site 空 node_modules 安装 | 2.33 s |
| API 空 node_modules 安装 | 0.86 s |

安装使用已有 npm 缓存，未声称测量完全冷网络缓存。复制组装不包括全部生产依赖，完整 release 构建在 AR-05 验收。API 最终采样与早期 projection profiling 存在重叠负载，保留原始范围而不挑选更快样本；AR-08 将在独立采样窗口复核容量。

冻结本地比较目标：并发 10 查询 P95 ≤ 200 ms、事件循环 P99 ≤ 50 ms；同版本轮询业务解析 0 次；完整分页重复/遗漏 0。生产资源与恢复预算保留待实际机器测量，不阻塞本地优化。

## 完整回归

命令：

```sh
env PATH="/Users/zhangchen/miniconda3/bin:$PATH" python3 scripts/architecture-regression.py --task AR-01
```

结果：**45 个检查组通过，0 失败，退出码 0，耗时 531.63 秒**。

- [退出码与日志校验摘要](./acceptance/AR-01/regression.json)
- [完整回归日志](./acceptance/AR-01/20261001T151413984312Z/regression.txt)
- [首次沙箱失败尝试](./acceptance/AR-01/failed-sandbox.txt)：回环监听 PermissionError，主动停止，未算成功。允许本地测试服务后完整重跑通过。

完整回归覆盖归档、价格证据、公开投影、发布事务、模型身份、站点构建/记录/交互/SEO/多语言、REST、MCP 与真实公开数据。没有使用跳过测试来取得成功状态。

## 未验证范围与后续

本轮未重新读取生产 current/共享 env，也未执行线上压测。基线工具的“新版本加载”成本采用完整冷加载作为代表；版本切换与乱序加载的实际行为由 AR-02 新测试验收。当前 public source 数据依赖 site 的现状已登记，AR-03 执行迁移。

无运行时配置变更，回退仅需撤回说明文档和基线工具。接下来执行 AR-02，优先实现版本检查与分批后台加载，避免一次转移整个 Dataset 造成新的主线程阻塞。
