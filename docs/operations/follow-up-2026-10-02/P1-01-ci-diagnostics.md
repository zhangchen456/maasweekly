# P1-01 CI 失败日志验收

本地实现完成；真实失败 CI 已确认原始日志与 metadata 进入 artifact，修复后的最终 CI 57/57 通过并发布。统一回归现在输出完整失败日志，不再只保留最后 25 行；原始日志与 suite/exitCode metadata 写到 runner 临时 artifact 根目录，由 always 上传步骤保留 14 天。成功时清理本次临时目录。失败、异常退出和中断保持原退出码与发布阻断；没有用自动重试掩盖失败。

新增执行级测试：早期断言 + 80 行后续输出仍可见、失败原始日志与真实退出码、成功清理/中断保留、工作流 always artifact 路径。3 项通过。最终完整本地回归 55 组通过、0 失败，详见 P1-01-tests.txt / P1-01-regression.txt。

第一次本地执行因运行时编辑脚本造成 Bash 读取错位而中断，未作为通过证据；固定最终入口后完整重跑通过。原中断记录保留为 P1-01-interrupted.txt。

首次线上 REST 偶发失败的具体原因仍未知，修复诊断不足不等于修复了未知业务缺陷。后续若复现，将有完整断言和原始日志可定位。

GitHub 首次拒绝 job 级 env 中的 runner.temp（HTTP 422）；生产未切换、采集未启动。已将日志根目录移至 Build release 步骤 env，增加禁止 job env 引用 runner.temp 的检查，重新提交验证。

真实 CI 37015172299：完整断言成功进入 artifact，定位到旧 fixture 继承 MAAS_REGRESSION_LOG_ROOT，仍在 TMPDIR 查找日志。已让 fixture 显式隔离两个目录；按相同 CI 环境复验 9 项通过。首次偶发 REST 故障仍未复现，不能把此次 fixture 修复作为其根因。最终候选 b5f299d185102e24e7544790060c263ccdd09443，工作流 37016897005 经队列执行后成功。

最终 CI 37016897005 成功：精确候选 b5f299d185102e24e7544790060c263ccdd09443 完整回归 57/57、0 失败，完成发布。修复后没有通过重试跳过断言。成功 artifact 归档 final-ci-artifact。
