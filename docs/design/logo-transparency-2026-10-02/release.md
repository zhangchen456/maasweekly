# 发布与验收

状态：RELEASED。2026-10-02。
代码 commit：`4e2496d2f82b75218c2fb4a02f228140f9a09367`；RID：`rl_4e2496d2f8_0da7f0c0f2bc`。
[正式CI](https://github.com/zhangchen456/maasweekly/actions/runs/36977021555) success；全量53/53、蓝绿激活、REST/MCP/RSS/Skill四入口门禁通过。CI原始构建与诊断artifact存于本目录ci-artifacts，步骤结果见ci-run.json。

本地站点构建与现有access-pages回归通过；本地与线上1440px/390px真实Chromium均无脚本错误、无文档横向溢出，客户端验证块消失，Codex TOML正常展开。PNG16/32/48及ICO的公网SHA256与本地一致，alpha范围0–255、角落alpha0；页面引用transparent-3资源。见local-browser.json、online-browser.json、online.json及对应截图。

数据版本保持 `ds_0da7f0c0f2bcd5df62281a262539b65a1742e3fbd710a14724359b58675c1b13`，dataThrough2026-10-02。图标与文案改动未改变API服务配置或业务数据。

必要时使用标准activator rollback至本次previous版本，然后执行四入口和页面验证。旧浏览器书签缓存可能在重新访问站点后才更新；站点已提供新的图标资源版本，服务器返回已确认透明。

主PNG：site/public/brand/icon-transparent.png。生成提示词与内置工具信息见README.md。临时验证脚本/本地构建完整日志已清理，验收摘要与正式CI原始artifact保留。
