# SEO 发布验收证据（2026-10-01，北京时间）

发布代码：`75b8a1d8c790f4ab6bd80c0988ca78884efbf0c7`。生产 release：`rl_75b8a1d8c7_1925cbc6adaf`。以下为标准本地构建与受限协议发布的实际输出。GitHub 重复任务 [36755033642](https://github.com/zhangchen456/maasweekly/actions/runs/36755033642) 已取消，不作为通过证据。

## 标准构建与全量回归

```text
[0/6] preflight
  ✓ commit 75b8a1d8c，工作区干净
[1/6] 公开数据投影
datasetVersion ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207 已发布且内容一致，零写入（幂等）
✓ 发布 ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207（changes=7166 items=7166 prices=1435 evidence=11288 weekly=23）dataThrough=2026-09-30
✓ 公开数据校验通过：ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207 · 7 文件 · dataThrough 2026-09-30
[2/6] 统一全量回归（Task 01–06）
══ Task 01–06 统一回归 ══
── export-public-data --check
   ✓ export-public-data --check
── validate-archive（Task 01）
   ✓ validate-archive（Task 01）
── validate-price-archive（Task 02）
   ✓ validate-price-archive（Task 02）
── build-skill-package --check
   ✓ build-skill-package --check
── test_record_archive（Task 01）
   ✓ test_record_archive（Task 01）
── test_price_archive（Task 02）
   ✓ test_price_archive（Task 02）
── test_public_export（Task 03）
   ✓ test_public_export（Task 03）
── test_skill_package（Task 04）
   ✓ test_skill_package（Task 04）
── test_release_build（Task 06）
   ✓ test_release_build（Task 06）
── test_release_activation（Task 06）
   ✓ test_release_activation（Task 06）
── test_deploy_mode（Task 06 M7）
   ✓ test_deploy_mode（Task 06 M7）
── test_model_identity_audit（Task 07）
   ✓ test_model_identity_audit（Task 07）
── test_model_public_projection（Task 07）
   ✓ test_model_public_projection（Task 07）
── test_model_registry（Task 07）
   ✓ test_model_registry（Task 07）
── validate-model-registry（Task 07）
   ✓ validate-model-registry（Task 07）
── audit-model-registry-coverage（Task 07）
   ✓ audit-model-registry-coverage（Task 07）
── test_workflow_release_contract（incident 2026-09）
   ✓ test_workflow_release_contract（incident 2026-09）
── validate-developer-registry（T07-5.2）
   ✓ validate-developer-registry（T07-5.2）
── test_developer_platform_registry（T07-5.2）
   ✓ test_developer_platform_registry（T07-5.2）
── test_analytics_foundation（T08-1A）
   ✓ test_analytics_foundation（T08-1A）
── test_umami_postgres_preflight（T08-1A）
   ✓ test_umami_postgres_preflight（T08-1A）
── test_umami_prerequisites（T08-1A）
   ✓ test_umami_prerequisites（T08-1A）
── test_inventory_capability（T08-1A Gate B Preflight）
   ✓ test_inventory_capability（T08-1A Gate B Preflight）
── site build（含 prebuild 门禁）
   ✓ site build（含 prebuild 门禁）
── site: access-pages（Task 05）
   ✓ site: access-pages（Task 05）
── site: rss（Task 05）
   ✓ site: rss（Task 05）
── site: pricing
   ✓ site: pricing
── site: model-identity-ui（T07-4A）
   ✓ site: model-identity-ui（T07-4A）
── site: model-identity-ui-contract（T07-4A）
   ✓ site: model-identity-ui-contract（T07-4A）
── site: changes-browser-contract（T07-4A.2）
   ✓ site: changes-browser-contract（T07-4A.2）
── site: changes-browser-ui（T07-4A.2）
   ✓ site: changes-browser-ui（T07-4A.2）
── site: model-detail（T07-4B.2）
   ✓ site: model-detail（T07-4B.2）
── site: analytics（T08 lightweight）
   ✓ site: analytics（T08 lightweight）
── site: agent-interactions（copy regression）
   ✓ site: agent-interactions（copy regression）
── site: platform-logos
   ✓ site: platform-logos
── site: leaderboards
   ✓ site: leaderboards
── site: records（含残留检测）
   ✓ site: records（含残留检测）
── site final build（测试 fixture 清理后）
   ✓ site final build（测试 fixture 清理后）
── site: SEO（canonical / sitemap / model content）
   ✓ site: SEO（canonical / sitemap / model content）
── agent-api: build
   ✓ agent-api: build
── agent-api: REST 测试
   ✓ agent-api: REST 测试
── agent-api: MCP 测试
   ✓ agent-api: MCP 测试
── agent-api: MCP 真实数据
   ✓ agent-api: MCP 真实数据
══════════════════════════
通过: 43 | 失败: 0
全部通过 ✓
[3/6] tracked diff 复查
[4/6] agent-api 生产包（完整编译 → omit=dev 裁剪）
[5/6] 组装 release
[6/6] manifest
✓ manifest: rl_75b8a1d8c7_1925cbc6adaf（22425 文件，644403194 字节）
✓ release 校验通过
✓ release rl_75b8a1d8c7_1925cbc6adaf → dist-release/rl_75b8a1d8c7_1925cbc6adaf
  datasetVersion=ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207 dataThrough=2026-09-30 commit=75b8a1d8c
```

## 生产激活与四入口验收

```text
✓ release 校验通过
2026/10/01 02:02:44 [warn] 2141076#2141076: conflicting server name "www.zhangchen456.xyz" on 0.0.0.0:80, ignored
2026/10/01 02:02:44 [warn] 2141076#2141076: conflicting server name "www.zhangchen456.xyz" on 0.0.0.0:443, ignored
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
2026/10/01 02:02:44 [warn] 2141077#2141077: conflicting server name "www.zhangchen456.xyz" on 0.0.0.0:80, ignored
2026/10/01 02:02:44 [warn] 2141077#2141077: conflicting server name "www.zhangchen456.xyz" on 0.0.0.0:443, ignored
2026/10/01 02:02:44 [notice] 2141077#2141077: signal process started
✓ activated rl_75b8a1d8c7_1925cbc6adaf
· ✓ 服务器 current: rl_75b8a1d8c7_1925cbc6adaf
· · 服务器 datasetVersion=ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207 / dataThrough=2026-09-30
· ✓ REST /api/v1/status datasetVersion=ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207
· ✓ REST /api/v1/changes?limit=10 datasetVersion=ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207
· ✓ MCP initialize 可达
· ✓ MCP 五工具齐备
· ✓ MCP 工具调用 datasetVersion=ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207
· ✓ RSS /feed.xml（rss+xml + ETag + 304）
· ✓ RSS /feed/weekly.xml（rss+xml + ETag + 304）
· ✓ Skill manifest + install.sh 可达
✓ 在线验收通过: current=rl_75b8a1d8c7_1925cbc6adaf / datasetVersion=ds_1925cbc6adaf0abb87106064c314e7b3d3bc513de2635b5e0aa2cf5bb5147207（REST+MCP+RSS+Skill 四入口）
```

## 线上 SEO 入口检查

以下入口实际 HTTP 200，响应正文与该 release 的本地验证产物逐字节相同：

- `/`、`/pricing/`、`/models/`
- `/robots.txt`：`text/plain`，含正式 sitemap URL
- `/sitemap.xml`：`text/xml`，7,074 个唯一正式网址
- `/model/deepseek:deepseek-v4-pro/`
- `/model/alibaba:qwen-plus/`
- `/model/alibaba:qwen3-coder-plus/`
- `/model/google:gemini-2.5-pro/`
- `/model/zhipu:glm-5.2/`

模型页核心正文无“加载中”，有静态价格记录和唯一 canonical；每页仅一个埋点适配器。`/pricing/?utm_source=seo-verification&modelId=alibaba%3Aqwen-plus` 的 canonical 为 `https://daily.maas.click/pricing/`。

浏览器状态读取两次超时，未完成真实浏览器视觉复核和 Search Console/百度后台登录与提交。自动交互测试验证刷新分页、网络失败及版本变化时保留静态内容；没有把 HTTP 读取当作真实浏览器验收。
