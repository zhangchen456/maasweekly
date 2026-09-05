# MaaS Weekly 交接文档（Handoff）

> 最后更新：2026-09-04
> 站点：**https://week.maas.click**（旧域名 https://mw.zhangchen456.xyz 同站保留）
> 仓库：https://github.com/zhangchen456/maasweekly
> 本地工作目录：`/Users/zhangchen/Work/maasweekly`

---

## 一、这是什么

AI 驱动的 MaaS 平台追踪站，两个内容层次：

1. **每日动态**（自动）：每天凌晨 05:00 自动抓取 17 个平台 + 行业信源（共 68 个 URL），与上一次快照逐行 diff，增量变化展示在 `/changes` 页，热点事件提炼到首页 LIVE 滚动条
2. **周度报告**（人工/Agent 写作）：完整行业周报，53 期历史存档（2025-10 ~ 2026-09），结构化渲染首页

运营状态：**全自动运行，日常无需人工介入**。人工要做的事只有一件——每周写周报（见第五节）。

---

## 二、架构与数据流

```
┌────────────── GitHub Actions（每日凌晨 05:00 北京时间）──────────────┐
│                                                                  │
│  fetch_sources.py          抓 68 个信源 → data/snapshots/日期/    │
│       ↓                  与最近快照 diff → data/diff/日期.md|json │
│  sync-diff-to-site.py      聚合最近 14 天 diff →                  │
│       ↓                  site/src/data/daily_changes.json         │
│  extract-live-events.py    从 diff 提炼发布/下线/调价事件 →        │
│       ↓                  site/src/data/live_feeds.json（≤20条）   │
│  fetch-images.py（可失败）  抓文章配图 og:image                    │
│       ↓                                                          │
│  astro build              29 页静态站 → site/dist/                │
│       ↓                                                          │
│  rsync（maasdeploy 受限账号）→ aliyun-099:/var/www/maasweekly/    │
│       ↓                                                          │
│  git commit + push         快照/diff/站点数据提交回仓库（明日基线）│
└──────────────────────────────────────────────────────────────────┘
```

三个工作流（`.github/workflows/`）：

| 工作流 | 触发 | 内容 |
|--------|------|------|
| `daily-update.yml` | 每日凌晨 05:00 定时 / 手动 | 全链路（上图）。手动可勾选 skip_fetch 只重新构建 |
| `deploy.yml` | push 到 main / 手动 | 仅构建+部署（1-2 分钟）。push 触发已排除 `data/**` 和 `site/src/data/**`（Actions 自动提交的数据，防止循环触发） |
| `weekly-update.yml` | 每周一 09:00 / 手动 | 三模式：aggregate（只抓取汇总）/ import（导入新周报并部署）/ full（全做） |

**注意**：`deploy.yml` 与 `daily-update.yml` 的 concurrency group 不同（deploy / daily-update），同一时间各只允许一个实例。

---

## 三、目录结构速查

```
maasweekly/
├── site/                        # Astro v7 站点
│   ├── src/content/weekly/          # 周报 Markdown（import-weekly.py 生成）
│   ├── src/content/weekly-structured/  # 周报结构化 JSON（extract-structured.py 生成）
│   ├── src/content/platforms/       # 每平台信源 JSON（split-sources.py 生成）
│   ├── src/data/
│   │   ├── daily_changes.json       # /changes 页数据源（sync-diff-to-site.py 产出）
│   │   ├── live_feeds.json          # 首页 LIVE 滚动条（extract-live-events.py 产出 + 可人工增改）
│   │   ├── leaderboards/ pricing/   # 榜单与价格静态数据（目前手工维护）
│   │   └── industry_sources.json    # 第三方渠道（split-sources.py 产出）
│   ├── src/pages/                   # index / changes / weekly/[id] / leaderboards / pricing / sources / about
│   └── scripts/                     # 站点侧脚本（见下表）
├── pipeline/
│   ├── scripts/
│   │   ├── fetch_sources.py         # 核心：抓取 + 快照 + diff
│   │   ├── sync-diff-to-site.py     # diff JSON → daily_changes.json
│   │   └── extract-live-events.py   # diff JSON → live_feeds.json 热点事件
│   └── config/maas_official_sources.json  # 信源总配置（改信源在这里）
├── data/
│   ├── snapshots/日期/               # 每日原始快照（diff 对比基线，勿删）
│   ├── diff/日期.md|json             # 每日变化报告（人读 + 机读）
│   ├── weekly/                       # 周报源文件（新周报写好放这里）
│   └── daily/ weekly-archive-early/  # 历史存档（只读）
└── .github/workflows/                # 三个工作流
```

**脚本一览**（都可用 `python3 <脚本路径>` 本地跑，路径已全部仓库相对化）：

| 脚本 | 位置 | 用途 | 调试参数 |
|------|------|------|---------|
| fetch_sources.py | pipeline/scripts | 抓全部信源产出 diff | `--platform 火山方舟` 单平台；`--max-sources 5` 限量 |
| sync-diff-to-site.py | pipeline/scripts | 聚合 diff 到站点 | 无 |
| extract-live-events.py | pipeline/scripts | 提炼 LIVE 事件 | 可传指定 diff.json 路径参数 |
| import-weekly.py | site/scripts | data/weekly → content/weekly | 无 |
| extract-structured.py | site/scripts | 周报 → 结构化 JSON | 无 |
| split-sources.py | site/scripts | 信源总配置 → 每平台 JSON | 无 |
| fetch-images.py | site/scripts | 抓文章配图 | `FETCH_IMAGES_PROXY` 环境变量可选代理 |

---

## 四、部署与服务器

**服务器**：aliyun-099（`ssh aliyun-099`，47.237.135.97，root，密钥 `~/Downloads/zhangchen.pem`）

| 项 | 值 |
|----|---|
| 站点根目录 | `/var/www/maasweekly/`（属主 maasdeploy） |
| nginx 配置 | `/etc/nginx/sites-available/maasweekly.conf`（双域名）+ `/etc/nginx/snippets/maasweekly-https.conf`（共享 HTTPS/缓存配置） |
| 证书 | certbot 自动续期：`/etc/letsencrypt/live/week.maas.click/` 与 `/etc/letsencrypt/live/mw.zhangchen456.xyz/` |
| 部署账号 | `maasdeploy`，登录 shell 是受限脚本 `/usr/local/bin/maasweekly-deploy-shell`（只放行 rsync --server，其余命令拒绝） |
| 部署私钥 | 本地 `~/.ssh/maasweekly-deploy-key`；GitHub Secret：`DEPLOY_SSH_KEY`（两边同钥） |

**双通道部署设计**（有意为之，勿"优化"掉）：

- 有服务器权限的人：本地 `cd site && npm run build && rsync -az --delete dist/ maasdeploy@47.237.135.97:/var/www/maasweekly/`
- 无服务器权限的协作者：push 到 main 自动触发 deploy.yml；或 Actions 页面手动触发（需要仓库 Write 权限）

**缓存策略**：`/_astro/`（带内容 hash）缓存一年 immutable；HTML `no-cache`——每日更新即时可见。

**本机注意**：直连 GitHub 会超时，git push 前先 `export https_proxy=http://127.0.0.1:7897 https_proxy=http://127.0.0.1:7897`。

---

## 五、日常操作手册

### 每天要做的事

**没有**。05:00 自动跑。想看结果：https://week.maas.click/changes 。Actions 执行记录：https://github.com/zhangchen456/maasweekly/actions

### 每周写周报（唯一的人工环节）

1. 素材：周一 09:00 的 weekly-update.yml 已自动抓好一周 diff；直接看 `data/diff/` 最近 7 天 + 上一期周报格式（`data/weekly/2026-09-01.md`）
2. 写新周报：`data/weekly/YYYY-MM-DD.md`，遵循固定六节结构（重要更新摘要/各平台详细追踪/状态汇总表/趋势洞察/关注时间点/已报道事件索引）——**结构化提取脚本依赖此格式，别改章节标题**
3. 上线：push 后到 Actions → 周报数据准备 → Run workflow → 选 `import` 模式；或等下周一自动 full
4. 验证：首页应显示新一期；`/weekly/YYYY-MM-DD` 详情页可访问

### 想立即让代码改动上线

push 到 main 即可（deploy.yml 自动触发，约 1.5 分钟）。或本地直连 rsync（见第四节）。

### 加/改/删一个信源

1. 编辑 `pipeline/config/maas_official_sources.json`（platforms 数组，sources 支持 model_list/pricing/changelog/api_docs/github/blog/model_marketplace 七个维度，可为 null）
2. 跑 `python3 site/scripts/split-sources.py` 更新站点信源页数据
3. push（自动部署信源页）；信源抓取无需重启任何东西，下次 05:00 生效

**加信源的经验**（踩过的坑）：

- SPA 页面（curl 拿到 <50 字符文本）直抓无效——先 `curl` 验证有静态内容再配置
- SPA 平台去找它的后端公开 API：从页面 JS bundle（`<script src>` 入口）grep `"/api/..."`，讯飞星辰 MaaS 的公告 API 就是这么找到的
- API 返回 JSON 时 fetch_sources.py 会自动格式化（URL 含 `/api/` 即命中）
- `notes` 字段记录探测结论（哪些可抓/为什么不可抓），给后来者省时间

### 人工修正 LIVE 滚动条

提炼是规则式的，偶尔误报/漏报。直接编辑 `site/src/data/live_feeds.json`：人工条目和自动条目会按 platform+标题去重合并（人工条目只要标题不同就共存）。push 即上线。

---

## 六、已知问题与技术债

按优先级排序，接手人按需处理：

1. **diff 噪声**：按行集合对比对部分 SPA/动态页面有误报（页面元素抖动算"变化"）。今天 27 个"变化"信源里估计有一部分是噪声。方案：跑一两周积累数据后，对高噪声信源加指纹过滤（只对比含模型名/价格模式的行）
2. **live 事件提炼准确率**：规则式约 80-90%。中文公告格式多样，已知漏报场景：不含"发布/上线"关键词的新模型公告。方案：积累误报样本后加规则，或换 LLM 提炼（Actions 里加一个 API 调用，有持续成本）
3. **讯飞星辰只有 changelog 信源**：模型列表/定价是 CSR 无公开 API。要覆盖需上 headless 浏览器（playwright），成本较高，价值待定
4. **榜单数据分两轨**：OpenRouter 四个数据集（调用量/厂商份额/会话成本/Top Apps）已接入自动抓取——`pipeline/scripts/fetch-leaderboards.py` 每日随 daily-update 运行（需 GitHub secret `OPENROUTER_API_KEY`；失败降级保留旧快照）。五个能力榜（LMArena/AA/SuperCLUE/SWE-bench/Terminal-Bench）仍为**手工维护**（JSON 带 `manual: true`），更新流程：改 `site/src/data/leaderboards/*.json` → 本地 `node site/tests/leaderboards.test.mjs` 验证 → push。**注意**：`site/src/data/**` 在 deploy.yml 的 paths-ignore 里，手工更新 JSON 后 push 不会触发自动部署——手动 workflow_dispatch 触发 deploy.yml，或等次日 05:00 daily-update 上线。数据来源：LMArena/SuperCLUE/SWE-bench/Terminal-Bench 快照可在 `data/snapshots/` 的每日抓取里找到现成素材（fetch_sources 已抓这两个信源页）
5. **fetch-images.py 依赖代理网络**：CI 里无代理，海外图片抓取部分失败（continue-on-error 不阻塞）。需要时设 `FETCH_IMAGES_PROXY`
6. **skill4u.conf.bak 被 include 产生 nginx warn**：服务器上老问题，与本项目无关但每次 nginx -t 都有警告，可顺手清理（把 .bak 移出 sites-enabled）

## 七、演进方向（原 GUIDE.md 中的规划）

- P2 板块：`/models`（模型动态）、`/capital`（资本动态）、`/community`（生态风向）——数据从周报与第三方渠道提取为结构化 JSON
- RSS 订阅（`@astrojs/rss`）
- 周报搜索/按平台筛选
- 周报 frontmatter 加 `summary` 字段做首页速览卡

---

## 八、快速排障

| 症状 | 排查 |
|------|------|
| 站点没更新 | Actions 页面看 latest run 是否失败；常见失败：信源全 429（次日自动恢复）、rsync 连不上（服务器网络/密钥） |
| Actions 卡在 Commit new data | git push 冲突（本地与远端同时有提交）→ 本地 `git pull --rebase` 再推 |
| /changes 页显示旧数据 | 看 `site/src/data/daily_changes.json` 的 updated_at；若旧，手动跑 sync-diff-to-site.py 后 push |
| LIVE 滚动条异常 | 看 `live_feeds.json`，对照 `data/diff/` 原始数据定位是提炼问题还是抓取问题 |
| 证书过期 | certbot 自动续期理论上不会；手动 `ssh aliyun-099 'certbot renew --dry-run'` 验证 |
| 新域名/新服务器迁移 | 改四处：DNS、nginx conf、astro.config.mjs 的 site、deploy.yml 的 env（DEPLOY_HOST/USER/PATH）+ 服务器部署账号 + GitHub Secret |
