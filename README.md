# MaaS Weekly

全球 MaaS 平台追踪站：周度报告 + 每日信源变化（热点每天更新），数据由自动抓取管线驱动。

线上地址：**https://week.maas.click** （`https://mw.zhangchen456.xyz` 为同站旧域名，保留可用）

部署：aliyun-099（47.237.135.97）nginx 静态站，目录 `/var/www/maasweekly`，由 GitHub Actions rsync 更新。

## 仓库结构

```
maasweekly/
├── site/                    # Astro v7 静态站点（GitHub Pages 部署）
│   ├── src/content/weekly/      # 周报 Markdown（带 frontmatter）
│   ├── src/content/weekly-structured/  # 周报结构化 JSON（extract-structured.py 生成）
│   ├── src/content/platforms/   # 平台信源 JSON（split-sources.py 生成）
│   ├── src/data/               # 榜单/定价/每日变化等数据源
│   └── src/pages/changes.astro # 每日动态页（消费 data/diff）
├── pipeline/                # 数据管线
│   ├── scripts/fetch_sources.py        # 每日抓取 16 平台 + 行业信源，快照 + diff
│   ├── scripts/sync-diff-to-site.py    # 聚合 diff JSON 到站点数据源
│   └── config/maas_official_sources.json  # 信源配置（67 个 URL）
├── data/                    # 抓取产物与历史数据（git 跟踪）
│   ├── snapshots/YYYY-MM-DD/    # 每日原始快照
│   ├── diff/YYYY-MM-DD.md|json  # 每日变化报告（人读 + 机读）
│   ├── weekly/                  # 周报源文件
│   ├── daily/                   # 早期每日追踪报告（7 月前）
│   └── weekly-archive-early/    # 更早期手写周报存档
└── .github/workflows/       # 自动化
    ├── daily-update.yml     # 每天 08:30 抓取 + 构建 + 部署
    └── weekly-update.yml    # 每周一 09:00 抓取汇总 + 周报导入 + 部署
```

## 自动更新机制

### 每日（热点信息每天更新）

`daily-update.yml` 每天北京时间 08:30 执行：

1. `fetch_sources.py` 抓取全部信源（模型列表 / 定价 / 更新日志 / 博客）
2. 与最近一次快照逐行 diff，产出 `data/diff/YYYY-MM-DD.md|json`
3. `sync-diff-to-site.py` 聚合最近 14 天 diff 到 `site/src/data/daily_changes.json`
4. Astro 构建，部署 GitHub Pages
5. 新快照与 diff 提交回仓库（作为明天的对比基线）

站点 `/changes` 页面按天展示每个平台的变化条目，点击展开新增/删除行。

### 每周（周报）

`weekly-update.yml` 每周一 09:00 抓取汇总素材。新周报写好后放入 `data/weekly/YYYY-MM-DD.md`，手动触发工作流选 `import` 或 `full` 模式，即导入站点（`import-weekly.py` + `extract-structured.py`）并部署。

## 本地开发

```bash
cd site
npm install
npm run dev      # http://localhost:4321/
npm run build    # 构建到 dist/

# 手动跑一次抓取（调试）
python3 pipeline/scripts/fetch_sources.py --platform 火山方舟   # 单平台
python3 pipeline/scripts/fetch_sources.py --max-sources 5      # 限量
python3 pipeline/scripts/sync-diff-to-site.py                  # 同步到站点
```

## 首次部署到 GitHub Pages

1. 新建 GitHub 仓库，推送本目录
2. 仓库 Settings → Pages → Source 选 **GitHub Actions**
3. 改 `site/astro.config.mjs` 的 `site` 字段为实际域名（默认 `https://<user>.github.io/<repo>/` 需加 `base: '/<repo>/'`，若用自定义域名则不用）
4. Actions 里手动触发 `daily-update.yml` 验证全链路

## 数据说明

- 信源配置：`pipeline/config/maas_official_sources.json`（国内 9 + 海外 7 平台，6 维度信源 + 行业数据源）
- diff 算法：按行集合对比，过滤 10 字符以下短行，噪声较多的页面（JS 渲染的 SPA）可能误报，后续可换 HTML 结构化 diff
- 历史周报：53 期（2025-10 ~ 2026-09），完整存于 `data/weekly/` 与 `data/weekly-archive-early/`
