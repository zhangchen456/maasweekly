# Task 05 结果报告：Agent 接入页、RSS 与方法说明

日期：2026-09-17。状态：**Task 05 本地实现完成（含复验修复）**——T01–T17、T19 全部通过；T18 真实阅读器保留为 Task 06 上线验收项。未 commit/push（等用户指示）。

## 1. 四种接入方式与当前状态

| 方式 | 状态 | 说明 |
| --- | --- | --- |
| RSS | pending（本地验证 ✓） | feed 本地构建与标准解析器验证通过；生产 URL 待 Task 06 部署并完成真实阅读器验收 |
| Skill | pending（双层：包可安装 · 查询待 REST） | 包 1.0.0 在线可下载；数据查询依赖 REST 生产路由（Task 06） |
| MCP | pending（本地验证 ✓） | Claude Code 2.1.259 真实验证通过；生产 /api/mcp 随 Task 06 |
| REST API | pending（本地完成） | 生产 /api/v1/* 随 Task 06 |

当前 release：`ds_fa0adf0f7593b4532421ae49e0bb8a2167c8d3167d1873519cc3398c68058b2b`（dataThrough 2026-09-16；changes 3181 / prices 1335 / evidence 6285 / weekly 23）。

## 2. 两个 feed

- **条数**：changes 100 条（≤100 上限）、weekly 23 期（≤30 上限）
- **GUID**：稳定 record ID / weekly ID（`isPermaLink="false"`），不含 datasetVersion/标题/排序/构建日期；修订保 GUID；withdrawn 退出默认 feed
- **时间精度**：真实数据混合形态——100 条中 78 条 datetime（RFC 822 UTC pubDate）+ 22 条 date 精度（**省略 pubDate**，描述保留「日期精度」说明）；weekly 全部省略（日期精度不合成午夜）；channel 无 lastBuildDate，dataThrough/datasetVersion 写在 description
- **字节稳定（T08）**：两次完整构建后 `cmp` 逐字节相同（构建级实测 + 单元级双调用断言 + 源码无时钟/随机）
- **标准解析器（T18 半项）**：fast-xml-parser（devDep）解析通过（结构/条数/GUID/链接/顺序全断言）；**真实阅读器导入受 localhost 限制，保留为 Task 06 上线验收项**（按任务书 §12，不冒充通过）

## 3. 页面与配置

- **`/agent/`**：七段（能问什么→四卡→配置安装→验证问题→成功示例→数据范围→故障恢复）；四卡 grid `minmax(min(100%,300px),1fr)`；示例回答从 release 确定性选取（不写死模型价格）；Skill 卡双层状态徽标；Codex 无「已支持」徽标
- **`/method/`**：八节方法说明；动态数字（dataThrough/3181/1335/6285/23）全部从 release 渲染，无构建时间戳
- **`/changelog/`**：首条真实记录（date: null →「随首次生产部署确定」不倒填）+ v1 兼容规则 + 无虚构 Sunset
- **`llms.txt`**：站点用途 + 快照声明 + 6 个正式入口链接（无数量、无客户端宣称）
- **CopyBlock.astro**：data 属性选择器（多实例安全），clipboard 失败 createRange 回退 + aria-live
- **单一配置 `public-access.ts`**：canonical/路径/状态/客户端唯一来源；astro.config import SITE_CANONICAL（实测可行）；门禁拒 localhost/file:///本机路径/未知状态；T01 漂移断言覆盖 openapi-v1.json servers、skill-version.json、llms.txt
- **导航**：nav +「接入」（6 项）+ 页脚 footer-meta（关于·接入·方法·变更·RSS）+ 480px gap 微调

## 4. 验收对照（T01–T19）

| # | 结果 | 测试 |
| --- | --- | --- |
| T01 | ✅ 配置门禁 9 违规样本逐项拒 + 漂移三向断言 + dist 9506 文件扫描无违规 | access-pages [1][2][3] |
| T02 | ✅ 四卡齐备 + 快照声明 + 无结果语义 | access-pages [4] |
| T03 | ✅ Claude Code 已验证徽标；Codex 待验证无徽标 | access-pages [4] |
| T04 | ✅ aria-live + 键盘 + 无 JS 5 代码块可读 + 剪贴板失败回退（实测） | access-pages [8] + Playwright |
| T05 | ✅ URL/版本/占位符/合同一致；pending 含 Task 06 说明 | access-pages [4] |
| T06 | ✅ RSS 2.0 / ≤100 / GUID 唯一稳定 / 顺序=重算 / 链接 dist 实存 | rss [1] |
| T07 | ✅ ≤30 期 / 无滚动摘要 / 倒序 / 链接实存 | rss [2] |
| T08 | ✅ 双构建 cmp 逐字节相同 + 单元双调用 + 源码扫描 | rss [7] + 构建级 |
| T09 | ✅ 修订保 GUID、内容更新；withdrawn 退出 | rss [4] |
| T10 | ✅ 混合精度（真实 78+22）+ 单元 date/datetime + 无午夜合成 + 无 build time | rss [3][5] |
| T11 | ✅ script/]]>/控制字符/超长注入后可解析、无未转义、截断 | rss [6] |
| T12 | ✅ feed+页面+llms.txt 链接遍历：内部 dist 实存、外部全 canonical | rss [9] + access-pages [7] |
| T13 | ✅ 八节齐备 + 动态数字=manifest + 无构建时间戳 | access-pages [5] |
| T14 | ✅ 首条真实 + 不倒填 + v1 规则 + 无虚构停用公告 | access-pages [6] |
| T15 | ✅ 320/375/1280 三页零横向溢出（Playwright 实测）+ Tab 键盘序列 + 焦点样式 + 复制反馈 | 自动 + Playwright |
| T16 | ✅ 目录缺失/hash 篡改 → throw [release]；正确 fixture 通过 | rss [8] |
| T17 | ✅ 本地 MCP 两问：变化查询（版本/截至/覆盖/真实数据）+ 价格→证据（币种/单位/完整条件含长短上下文档位区分/观察时间） | headless Claude Code |
| T18 | 🔶 标准解析器 ✅（fast-xml-parser）；真实阅读器=Task 06 项 | rss [1][2] |
| T19 | ✅ 全量回归全绿（复验修复后含此前失败的两测试，见 §6 P1-3） | — |

## 5. 测试命令与结果

| 命令 | 退出码 |
| --- | --- |
| `python3 pipeline/scripts/export-public-data.py --check` | 0 |
| `python3 -m unittest discover -s tests -p 'test_public_export.py' -v` | 0（12 项） |
| `python3 -m unittest discover -s tests -p 'test_skill_package.py' -v` | 0（21 项） |
| `python3 -m unittest discover -s tests -p 'test_price_archive.py' -v` | 0（56 项） |
| `cd services/agent-api && npm test` | 0（26 项） |
| `npm run test:mcp` | 0（13 项） |
| `npm run test:mcp:real` | 0（8 项） |
| `cd ../../site && npm run build` | 0（9501 页 / 18.9s） |
| `node --experimental-strip-types tests/access-pages.test.mjs` | 0（55 项检查） |
| `node --experimental-strip-types tests/rss.test.mjs` | 0（35 项检查） |
| `node tests/pricing.test.mjs` | 0 |
| T08 双构建 `cmp` | 逐字节相同 |
| T15 Playwright（320/375/1280 × 3 页 + 键盘 + 无 JS） | 0 溢出 / 正常 |

## 6. 复验修复（2026-09-17 验收驳回后）——三项 P1 全部关闭

### P1-1 公开 release 完整性校验绕过

- **原缺陷**：loadVerifiedRelease 只校验 manifest.files 已列出的文件——
  manifest.files 清空 + 目录写入未签名 changes.json 时仍加载 TAMPERED 内容。
- **修复**（site/src/lib/release.ts 重写校验链，全部通过后才解析）：
  select 请求的文件必须在 manifest.files 恰好出现一次；全部清单条目
  路径必须在 releases/{datasetVersion}/ 下（拒绝对路径/../逃逸/版本错位）；
  datasetVersion 格式校验（ds_<64hex>）；bytes + SHA-256 校验通过后才
  JSON.parse；错误信息只含相对路径与规则名。
- **攻击复现**：原攻击场景（空 manifest + 未签名 changes.json）→
  `[release] 请求加载的文件不在 manifest 清单（构建中止）` ✓
- **反例测试**（rss.test.mjs [8] 段，11 项）：清单删除/条目重复/../逃逸/
  版本错位/bytes 篡改/hash 篡改/版本格式非法 → 全部拒绝；合法
  changes+weekly 双集合正常加载；错误零路径泄漏。

### P1-2 RSS 未部署却标记 available

- public-access.ts：RSS → pending（locallyVerified: true），reason 写明
  「feed 本地构建与标准解析器验证通过；生产 URL 待 Task 06 部署并完成
  真实阅读器验收后可用」；changelog.ts rss area 同步 pending。
- agent.astro RSS 卡补 card-note（渲染 reason）；access-pages 新增两条
  断言（RSS 卡显示待部署且不伪装已上线 + 含真实状态原因）。
- Task 06 部署并验证线上 URL 后才改回 available（仍只改配置一处）。

### P1-3 两个失败测试（真实数据修复，非绕过）

- **platform-logos**：Descript 与 Upstage（前者挡住后者）均按既有规则从
  官方站取 256px apple-touch-icon（非占位图），hash 后缀入库 + registry
  条目（source_url/sha256/bytes 完整）。
- **leaderboards**：五家手工榜全部从官方来源获取真实数据：
  - lmarena：data/snapshots/2026-09-16 每日抓取快照（既定可信来源）解析
    Text Overall 榜（elo 逐条来自快照原文）；
  - aa / swebench / terminal-bench / superclue：各自官方站 Playwright
    实时渲染取榜（与管线抓取同通道）；AA 为 Intelligence Index v4.3
    （9 月指数升版，53 分制与旧 66 分制不可比——note 如实标注）。
  - 未改任何日期绕过 freshness 门禁；全部 2026-09-17 快照。

### 回归（复验修复后全绿）

export --check + Python 107 项（12+21+56+18）+ agent-api 47 项
（26+13+8）+ site 构建 + **六个 site 测试全部通过**（此前失败的
platform-logos 与 leaderboards 已修复）。

## 6b. 已知限制（如实）

1. **T18 真实阅读器**：localhost 无法被外部阅读器访问——保留为 Task 06 上线验收项。
2. **静态产物无响应头**：Content-Type/Cache-Control/ETag 由 Task 06 生产服务器验收。
3. **Task 04 遗留**：Codex 客户端验证仍待 OpenAI 认证环境（接入页/changelog/llms.txt 均如实标注待验证）。
4. **手工榜维护依赖**：五个手工榜单（lmarena/aa/swebench/terminal-bench/superclue）无管线自动抓取，10 天新鲜度门禁需定期人工更新（本次全部更新至 2026-09-17）。

## 7. Task 06 上线阻断项清单

1. 生产 /api/v1 与 /api/mcp 路由（agent-api 常驻 + nginx 反代）
2. feed 的 Cache-Control ≥30min + ETag/304 + Content-Type 验收
3. 真实 RSS 阅读器导入验收
4. Codex 客户端验证（OpenAI 认证环境）
5. 单一配置状态翻转（REST/MCP/Skill pending → available，只改 public-access.ts 一处）

## 8. 本地体验

```bash
cd site && npm run build && npx astro preview
# /agent/ /method/ /changelog/ /feed.xml /feed/weekly.xml /llms.txt
node --experimental-strip-types tests/access-pages.test.mjs
node --experimental-strip-types tests/rss.test.mjs
```
