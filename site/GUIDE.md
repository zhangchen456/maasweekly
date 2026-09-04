# MaaS Weekly 站点导览

> 本地路径: `work/maas/maas-weekly-site/`
> 技术栈: Astro v7 静态站点生成器
> 数据来源: `cronjob/reports/maas-platform/weekly/` (周报) + `maas_official_sources.json` (官方信源) + `src/data/` (第三方渠道/榜单/算力数据)

---

## 快速命令

```bash
cd work/maas/maas-weekly-site

npm run dev      # 本地预览 http://localhost:4321/
npm run build    # 构建到 dist/
npm run preview  # 预览构建产物
```

---

## 目录结构

```
maas-weekly-site/
├── astro.config.mjs          # Astro 配置（site URL 在这里改）
├── package.json              # 依赖：astro ^7.2.10
├── tsconfig.json
│
├── src/
│   ├── content.config.ts     # Content Collection schema 定义（weekly + platforms）
│   │
│   ├── content/
│   │   ├── weekly/           # 23期周报 Markdown（2026-05-03 ~ 2026-09-01）
│   │   │   └── YYYY-MM-DD.md # 每期一个文件，带 frontmatter（title/date/period）
│   │   └── platforms/        # 16个平台信源 JSON（每个平台一个文件）
│   │       ├── volcengine.json
│   │       ├── alibaba.json
│   │       ├── ... (共16个)
│   │       └── google-google-vertex-ai.json  # Google 两个平台，Vertex AI 用全名区分
│   │
│   ├── data/
│   │   ├── industry_sources.json       # 第三方追踪渠道（21个，按 6 类分组 + 可获取性标记）
│   │   ├── leaderboards/               # 能力榜单数据（openrouter / lmarena / aa）
│   │   │   ├── openrouter.json         #   OpenRouter 调用量 Top10（7 日窗口）
│   │   │   ├── lmarena.json            #   LMArena Elo 榜快照
│   │   │   └── aa.json                 #   Artificial Analysis 智能指数快照
│   │   └── pricing/                    # 价格与算力数据
│   │       ├── api.json                #   API 定价对比（周报核验条目）
│   │       ├── gpu.json                #   GPU 租赁行情
│   │       └── chips.json              #   国产 AI 芯片动态
│   │
│   ├── layouts/
│   │   └── Layout.astro      # 全局布局：header + footer + 暗色主题 + Markdown 样式
│   │
│   └── pages/
│       ├── index.astro       # 首页：板块入口 + 最新一期 + 历史周报网格 + 平台标签
│       ├── weekly/[id].astro  # 周报详情页（动态路由，按 Markdown 文件名生成）
│       ├── leaderboards.astro # 能力榜单页：OpenRouter / LMArena / AA 三榜
│       ├── pricing.astro      # 价格算力页：API 定价 + GPU 行情 + 国产芯片
│       ├── sources.astro      # 信源目录页：平台分组 + 第三方渠道分组 + 可获取性徽标
│       └── about.astro        # 关于页
│
├── scripts/
│   ├── import-weekly.py       # 把 Obsidian 周报 Markdown 拷过来 + 加 frontmatter
│   └── split-sources.py       # 把 maas_official_sources.json 拆成单平台 JSON
│
├── public/                    # 静态资源（favicon）
└── dist/                      # 构建产物（npm run build 生成）
```

---

## 数据说明

### 周报（weekly collection）

- 位置：`src/content/weekly/YYYY-MM-DD.md`
- 来源：从 `cronjob/reports/maas-platform/weekly/` 导入
- frontmatter 字段：`title` / `date` / `period`（追踪周期）
- 新增周报：把 Markdown 文件放进 `src/content/weekly/`，顶部加 frontmatter 即可
  ```markdown
  ---
  title: "MaaS 平台周度追踪报告 - 2026-09-08"
  date: "2026-09-08"
  period: "2026-09-01 ~ 2026-09-08"
  ---
  ```

### 平台信源（platforms collection）

- 位置：`src/content/platforms/*.json`
- 来源：从 `maas_official_sources.json` 拆分
- 每个平台一个 JSON，schema：name / name_en / region / vendor / official_site / sources(6维度) / notes
- 国内9：火山方舟、阿里百炼、百度千帆、腾讯混元、硅基流动、智谱AI、Kimi、MiniMax、DeepSeek
- 海外7：OpenAI、Anthropic、Google Gemini API、Google Vertex AI、Mistral、Cohere、xAI

### 第三方追踪渠道（industry_sources.json）

- 位置：`src/data/industry_sources.json`（不在 content collection 里，sources.astro 直接读文件）
- 21 个渠道，按 6 类分组：第三方评测/榜单（5）、开发者社区（3）、融资/IPO/财报（5）、学术动态（2）、算力/硬件（2）、行业媒体（3）+ 政策信号（1）
- 每个渠道带 `type`（分类）、`accessibility`（可获取性：可直接抓取 direct / 需搜索聚合 search / 需浏览器 browser / 定时任务 cron）、`value`（信息价值标签）
- 可获取性徽标：绿=可直接抓取（定时脚本可拉）、黄=需搜索聚合、红=需浏览器、蓝=定时任务

### 榜单数据（leaderboards/）

- 位置：`src/data/leaderboards/*.json`（能力榜单页直接读文件）
- 统一 schema：`source` / `source_url` / `snapshot_date` / `note` / `top[]`（rank/model/vendor/值/备注）
- OpenRouter 按 token 处理量（反映开发者采用），LMArena 按 Elo（反映人类偏好），AA 按智能指数（综合基准）
- 更新方式：每周抓取替换 JSON 数值，改 `snapshot_date`

### 价格与算力数据（pricing/）

- 位置：`src/data/pricing/*.json`
- `api.json`：各平台 API 定价，标注 verified（周报核验）/ pending（待核验）
- `gpu.json`：国内 GPU 租赁行情（时租/包月，注明来源平台）
- `chips.json`：国产 AI 芯片动态（公开报道数据，带来源）

---

## 页面说明

| 页面 | URL | 说明 |
|------|-----|------|
| 首页 | `/` | 板块入口 + 最新一期高亮卡片 + 历史周报网格 + 追踪平台标签 |
| 周报详情 | `/weekly/YYYY-MM-DD` | 完整周报 Markdown 渲染 |
| 能力榜单 | `/leaderboards` | OpenRouter 调用量 / LMArena Elo / AA 智能指数 三榜交叉 |
| 价格与算力 | `/pricing` | API 定价对比 + GPU 租赁行情 + 国产芯片动态 |
| 信源目录 | `/sources` | 平台分组 + 21 个第三方渠道分组 + 可获取性徽标 |
| 关于 | `/about` | 覆盖范围、追踪维度、更新频率 |

---

## 脚本说明

### import-weekly.py — 导入周报

```bash
python3 scripts/import-weekly.py
```

- 读取 `cronjob/reports/maas-platform/weekly/*.md`
- 提取标题和追踪周期，生成 frontmatter
- 写入 `src/content/weekly/`
- 可重复运行，覆盖旧文件

### split-sources.py — 拆分信源

```bash
python3 scripts/split-sources.py
```

- 读取原始 `maas_official_sources.json`（路径在脚本里硬编码）
- 拆成每个平台一个 JSON 文件
- 同 vendor 多平台（如 Google Gemini + Vertex AI）用 name_en 区分文件名
- 清空旧文件后重写

---

## 部署

### 改域名

编辑 `astro.config.mjs`，把 `site` 改成实际域名：

```js
export default defineConfig({
  site: 'https://your-domain.com',
  ...
});
```

### 部署到服务器

```bash
npm run build                          # 生成 dist/
scp -r dist/* user@server:/var/www/maas-weekly/  # 拷到服务器
# nginx 配置 root 指向 dist 目录
```

---

## 后续可扩展

1. **模型动态 / 资本动态 / 生态风向板块**：规划 v1.0 的 P2 板块（`/models`、`/capital`、`/community`），数据从周报与第三方渠道提取为结构化 JSON
2. **自动更新闭环**：cron 定时抓取榜单/定价数据 → 写入 `src/data/` → `npm run build` → 部署
3. **RSS 订阅**：加 `@astrojs/rss` 集成
4. **搜索/筛选**：按平台名/日期过滤周报
5. **周报 summary 字段**：frontmatter 增加 `summary`，首页做速览卡
