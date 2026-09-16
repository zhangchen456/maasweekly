# Task 04 结果报告：MCP 与可安装 Agent Skill

日期：2026-09-16。状态：实现与本地验证完成（含复验修复）；**Codex 客户端兼容验收待完成（阻断项，见 §6b）**；生产 `/api/mcp` 部署属 Task 06。未 commit/push（等用户指示）。

## 1. 交付文件

```text
services/agent-api/src/
  mcp.ts                # 传输层：POST-only/独立限流/Origin/body limit(256KiB)/每请求 stateless server+transport/no-store
  mcp-tools.ts          # 五工具 zod schema + callMaasTool + 中文渲染器（无传输依赖）
  query.ts              # +LimitPolicy（REST 20/100、MCP 10/30）+runListQuery（从 http.ts 提取，REST/MCP 单一实现）
  http.ts               # TokenBucket 导出；handleList 改调 runListQuery；BASE_URL 常量化
  public-consts.ts      # PUBLIC_BASE_URL 单一来源
  server.ts             # dispatcher 挂 /api/mcp；MCP_* env
  tests/mcp.test.ts     # T01/T04-T12（13 项：SDK Client + 裸 fetch 双层，双 datasetVersion）
  tests/mcp-real.test.ts# T02/T03（7 项：真实 release，REST/MCP deepEqual）
agent-skill/maas-daily/ # SKILL.md + references/{api,errors}.md + README + LICENSE + skill-version.json + agents/openai.yaml
site/scripts/build-skill-package.py  # 包构建（manifest 可复现 + --check 源漂移门禁）
site/scripts/install-skill.sh        # 安装器（--dir 必选/全量校验/原子替换/故障恢复）
site/public/maas-skill/              # 发布包（manifest.json + install.sh + 7 文件，已入 build 链）
tests/test_skill_package.py          # T13-T17（19 项）
docs/contracts/mcp-v1.md
```

## 2. 架构决策与锁定版本

- **SDK**：`@modelcontextprotocol/sdk@1.30.0`（zod 4.6.5 随依赖树）。stateless
  （`sessionIdGenerator: undefined`）+ `enableJsonResponse: true`；每请求全新
  McpServer + transport（官方范式）；protocolVersion 由 SDK 协商（LATEST
  2025-11-25）。1.30 的 registerTool 签名与 1.29 一致（zod raw shape，无
  rawInputSchema——M1 spike 实读 d.ts 确认）。
- **D2 查询复用**：`runListQuery` 从 http.ts 提取到 query.ts（normalizeQuery →
  cursor 校验/版本固定/恢复重验 → list 单一实现）；REST 与 MCP 调用同一函数，
  仅 LimitPolicy 不同——T03 一致性由 deepEqual 证明。
- **structuredContent 与 REST 响应体逐字段同构**——最强的可证明一致性。
- **工具错误**：`isError: true` + `structuredContent.error{code,detail,recovery}`
  （code 与 REST Problem 同源），不用 McpError 抛协议层错误。

## 3. 命令与退出码（全部实际执行）

| 命令 | 退出码 |
| --- | --- |
| `python3 pipeline/scripts/export-public-data.py --check` | 0 |
| `python3 -m unittest discover -s tests -p 'test_public_export.py' -v` | 0（12 项） |
| `python3 -m unittest discover -s tests -p 'test_skill_package.py' -v` | 0（19 项） |
| `python3 -m unittest discover -s tests -p 'test_record_archive.py' -v` | 0（18 项） |
| `python3 -m unittest discover -s tests -p 'test_price_archive.py' -v` | 0（56 项） |
| `cd services/agent-api && npm ci` | 0 |
| `npm test` | 0（26 项：Task 03 全回归） |
| `npm run test:mcp` | 0（13 项） |
| `npm run test:mcp:real` | 0（8 项，含 T02b 七模式覆盖断言，真实 `ds_fa0adf0f…`） |
| `cd ../../site && npm ci && npm run build` | 0（9498 页 / 17.9s，含 build:skill） |

## 4. 验收对照（T01–T19）

| # | 场景 | 结果 | 测试 |
| --- | --- | --- | --- |
| T01 | initialize→tools/list | ✅ 恰 5 工具；schema 含精确/包含/默认10 说明 | mcp.test |
| T02 | 五工具真实数据 + 文本/结构一致 | ✅ 五工具+weekly 三模式文本均含版本/截至/实际覆盖（T02b 逐一断言） | mcp-real 8 项 |
| T03 | REST/MCP 同条件一致 | ✅ deepEqual（changes×3 组/prices 精确+包含/weekly/翻页顺序） | mcp-real |
| T04 | 默认10/上限30/组合/空结果/翻页 | ✅ 无重复遗漏；空结果合同措辞 | mcp.test |
| T05 | prices 条件完整不选最低 | ✅ CNY/contextBand/timeCondition/「未按价格排序」 | mcp.test |
| T06 | item→evidence 闭环 | ✅ 恶意摘录原样数据；withdrawn 可读 | mcp.test |
| T07 | weekly 最新/指定/列表/互斥 | ✅ 「滚动摘要不是周报」声明 | mcp.test |
| T08 | 错误稳定 code+恢复 | ✅ no_data_available 禁模型补答 | mcp.test |
| T09 | 协议错误/超大 body | ✅ -32700/-32601/415/406/413；进程存活；无泄漏 | mcp.test |
| T10 | Origin | ✅ 缺省放行/白名单/403 无副作用 | mcp.test |
| T11 | 热重载/损坏旧版 | ✅ 单调用不混版；坏旧版 getOrLoad null | mcp.test |
| T12 | 注入文本 | ✅ 原样数据，无执行路径 | mcp.test |
| T13 | Skill 路由与措辞 | ✅ 程序化检查（frontmatter/五意图/合同措辞/yaml 无 secret） | test_skill_package |
| T14 | manifest 可复现 | ✅ 两次构建逐字节相同；无墙钟/临时路径 | test_skill_package |
| T15 | 首装/幂等/升级/拒覆盖 | ✅ 其他 Skill 与未知文件不动 | test_skill_package |
| T16 | 下载/校验/缺文件/中断恢复 | ✅ 旧版逐字节完好；残留恢复 | test_skill_package |
| T17 | 错误目标/只读/symlink 逃逸 | ✅ 零写入；无 sudo；无遥测 | test_skill_package |
| T18 | 客户端验证 | 🔶 **Claude Code 完成；Codex 待完成（见 §6）** | 人工（见下） |
| T19 | Task 03 全量回归 + 站点构建 | ✅ 全绿（105 项测试 + 门禁 + 9498 页） | 本节命令 |

## 5. Claude Code 客户端验证（T18 已完成部分）

- **客户端**：Claude Code CLI **2.1.259**（darwin）；配置方式
  `claude --mcp-config <临时文件> -p`（Streamable HTTP，`-p` 每次即新会话）；
  服务器：本地 `node dist/server.js`（真实 release ds_fa0adf0f…）。
  用户全局配置零写入（临时 mcp.json 用后即删）。
- **工具发现**：5 个 maas_* 工具全部可见 ✅
- **四类真实问题**：
  1. 「最近几天 OpenAI 有什么变化」→ 返回 9-10 至 9-16 覆盖内的真实降价事件
     （gpt-6-astra input 40→10 等），区分「价格事件 vs 官方公告」✅
  2. 「gpt-6-astra 输入价格」→ $40 USD/1M token + region/billingMode/tier 完整条件
     + 观察时间 + 证据 ID（**如实标注 partial**）✅
  3. 「最新一期周报头条」→ 正式 2026-09-01 期（非滚动摘要）✅
  4. 「该证据的摘录」→ 摘录内容 + 定位（table:nth-of-type(4)）+ 来源 ✅
- **反伪造**：「xyz-totally-fake-model 价格」→ 如实返回空结果并说明数据集范围，
  未用模型知识编造 ✅（还正确建议了 q 模糊匹配）
- 已知限制：headless 模式下的非交互验证（无人工多轮对话压力测试）。

## 6. Codex 客户端验证——**待完成（Task 06 前阻断项）**

本机无独立 `codex` CLI（仅 ChatGPT 桌面 App 内置组件，无法程序化驱动真实
新会话）。按任务书 §7：实现/SDK 客户端测试/配置样例已交付（README 的
config.toml 片段），但**不以 fixture 或 curl 冒充客户端验证**。

**未完成清单**：Codex 新会话发现 Skill 或 MCP + 四类真实问题链路。
解除条件：安装独立 Codex CLI，或生产 /api/mcp 部署后在有 Codex 的环境验证。

## 7. 已知限制

1. 生产 `/api/mcp` 未部署（Task 06）——当前仅本地 127.0.0.1 可用；
   Skill 包内的公开地址在 Task 06 部署后生效。
2. `site/public/maas-skill/` 是构建产物入库（与 openapi-v1.json 惯例一致）；
   源在 `agent-skill/maas-daily/`——`build-skill-package.py --check` 已做
   源漂移门禁（源变包未重建 → 失败），且已接入 site build 链。
3. MCP 限流为进程内令牌桶；nginx 层限流留 Task 06。
4. 安装器未在 Linux（GNU 工具链）验证（本机 macOS BSD）；可移植封装
   （shasum/mktemp）已做，Linux 验证留部署时。
5. `maas_get_weekly` 的 zod 互斥校验（id vs limit/cursor）在 SDK 层返回
   -32602 而非工具错误——协议合规但错误码层级与 REST 不同（合同已记录）。

## 8. 本地体验

```bash
# MCP 服务（本地真实数据）
cd services/agent-api && npm run build && npm start   # 127.0.0.1:8787
curl -X POST http://127.0.0.1:8787/api/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Claude Code 接入（临时配置）
claude --mcp-config <(echo '{"mcpServers":{"maas-daily":{"type":"http","url":"http://127.0.0.1:8787/api/mcp"}}}') \
  -p "用 maas-daily 查 gpt-6-astra 的输入价格"

# Skill 包构建与校验
python3 site/scripts/build-skill-package.py --check
```


## 9. 复验修复（2026-09-16 验收驳回后）

验收发现两个 P1（未被原测试覆盖）与两个 P2，已修复：

### P1-1 安装器会删除同名 Skill 中的未知文件

- **原缺陷**：目标 SKILL.md 名为 maas-daily 时直接整目录替换——用户自建文件
  （如 user-config.md）在「升级」时被静默删除，退出码还是 0。违反任务书
  「未知文件拒绝覆盖」与 US-10。
- **修复**：目标判定段升级——合法同名时清点目标内全部文件，必须属于
  「新 manifest 已列 ∪ 旧 manifest 已列 ∪ manifest.json」，出现任何未知文件
  → 退出 5 拒绝覆盖（保护用户数据）。
- 测试：`test_upgrade_preserves_unknown_user_files`（安装→用户加
  user-config.md→重装→退出 5 且目录逐字节不变）。

### P1-2 工具文本缺少版本/数据时间/覆盖（两轮修复）

- **原缺陷（第一轮）**：maas_get_item/evidence/weekly 直接用各自渲染
  函数，没有公共 header——文本缺版本与 dataThrough。
- **第一轮修复**：三工具加 header(ds)。
- **复验仍不完整**：仅 changes 有查询窗口、默认周报有覆盖行；prices/
  item/evidence/指定周报/周报列表仍缺实际 coverage。
- **第二轮修复（最终）**：新增统一 `renderCoverage(ds)`——从
  ds.coverage（REST 同源元数据）提取实际覆盖（变化日期范围与计数、
  价格当前事实数、证据数、周报期数与最新期），**全部成功工具文本共用**
  `header + renderCoverage + 具体渲染`；weekly 三种模式与 changes/
  prices 列表同样适用。
- 测试（T02b）：五个工具 + weekly 三种模式（默认/指定/列表）共 7 个
  模式逐一断言「数据版本/数据截至/实际覆盖/快照声明」四要素。

### P2-1 --version 静默装错版本

- **原缺陷**：`--version 9.9.9` 实际安装 manifest 的 1.0.0 却打印
  「9.9.9 已安装」。
- **修复**：请求版本与 manifest 不一致 → 退出 4 并说明 manifest 仅有的
  版本（v1 单版本发布；真多版本留待需要时实现 releases/<v>/ 路径规则）。
- 测试：`test_version_mismatch_rejected`。

### P2-2 测试依赖未声明的 PyYAML

- **原缺陷**：裸 `/usr/bin/python3` 跑 test_skill_package.py 报
  ModuleNotFoundError: yaml（本机 Miniconda 才有）。
- **修复**：openai.yaml 检查改为行级断言（键存在 + 敏感词扫描），
  零第三方依赖。`/usr/bin/python3` 实测 21 项通过。

### 回归（修复后全绿，两种 Python）

系统 Python（无 PyYAML）与 Miniconda Python 各跑 21 项 Skill 测试通过；
Python 105 项（12+21+18+56 调整后）；TS 46 项（26+13+7）；export/skill
双 --check；site 9498 页构建。

## 6b. Codex 验证进展（2026-09-16 复验后）

按用户指示安装了独立 Codex CLI 0.154.0（npm 全局）并配置临时
CODEX_HOME（不碰 ~/.codex 桌面配置）：MCP 服务器（本地 agent-api）配置
就绪、`codex exec` 可达——但 **OpenAI 认证缺失（401）**，用户选择暂不
提供凭证，Codex CLI 已卸载、临时环境已清理。

**当前状态**：Codex 验证仍为阻断项。解除条件与操作序列（已验证可行）：
1. `npm i -g @openai/codex`
2. `CODEX_HOME=<临时目录> codex login`（ChatGPT 账号或 API key）
3. 临时 config.toml 写 `[mcp_servers.maas-daily] url="http://127.0.0.1:<port>/api/mcp"`
4. `CODEX_HOME=<临时目录> codex exec --skip-git-repo-check "<四类问题>"`
