# 自动更新链路故障记录（2026-09）

## 现象

GitHub Actions 持续报红：

- `每日信源抓取与站点更新: All jobs have failed`
- `周报数据准备: All jobs have failed`

但仓库证据表明抓取层正常：

- 数据提交仍在继续（9-20 / 9-21 每日信源抓取 + 9-21 周报）
- 最新一次 daily 抓取：total 68 / success 67 / failed 1 / changed 18
- `daily_changes` date = 2026-09-22

而 public projection 落后：

- `data/public/v1/manifest.json`：datasetVersion = ds_24f83f7e… / dataThrough = 2026-09-20
- 仓库数据已到 9-22，projection 至少落后 2 天

## 根因

daily / weekly workflow 的 step 顺序有问题：

```
抓取 → sync → 各类数据生成 → Commit new data → deploy-release.sh
```

`deploy-release.sh` 调用 `scripts/build-release.sh`，后者流程：

```
[0/6] preflight
[1/6] export-public-data.py        ← 根据新抓取数据生成 data/public/v1/*
[2/6] run-all-tests（含 site build）← 生成 site/src/data/pricing/*.html、site/public/maas-skill/*
[3/6] tracked diff 复查             ← 发现工作区变脏，拒绝构建
```

**Commit new data 只提交了 `data/ site/src/data/`（原始抓取数据），没有在 commit
前生成由数据驱动的 tracked 产物**：

1. `data/public/v1/`（export-public-data.py 生成的 public projection）
2. `site/src/data/pricing/price-ledger.rendered.html` + `price-ledger.fragment.html`
3. `site/public/maas-skill/`（build-skill-package.py 生成的 skill 包）

这些是 tracked 文件。build-release [1/6] / [2/6] 会重新生成它们，然后 [3/6]
tracked diff gate（`git status --porcelain` 必须为空）拒载。

**实际链路**：

```
抓取成功 → 数据提交成功 → build-release 生成 projection → 发现未提交 → 拒载 → job 红 → 无 activate
```

这解释了为什么 daily 和 weekly 都系统性失败，但抓取与数据提交正常。

### 为什么 projection 落后 2 天

每次 daily run：数据提交了，但 projection 因 build-release 拒载未发布。
下一次 daily run 基于已提交的新数据，build-release [1/6] 生成新 projection，
但 [3/6] 仍因"上次没提交的 projection + 这次 site build 产物"变脏而拒载。
projection 卡在上次成功 activate 的版本（9-20）。

## 修复

### 原则

不删除 tracked diff gate（它是正确的）。正确做法是：所有数据驱动的 tracked
产物必须在 release 构建前完整生成并提交。

最终链路：

```
抓取 / sync / import
  ↓
Prebuild site artifacts（fragment/rendered/skill 包）
  ↓
Export public data + Validate（--check）
  ↓
git add 所有数据 + projection + site 产物
  ↓
git commit + push
  ↓
deploy-release.sh --commit <精确 SHA>
  ↓
build-release 重算 projection + site build → 应产生零 tracked diff
  ↓
全量 tests → activate → online verify
```

### daily-update.yml

- Commit 前新增 `Prebuild site artifacts`（build-price-fragment / render-price-ledger / build-skill-package）
- Commit 前新增 `Export public data` + `Validate public data`（--check）
- `Commit` 步骤去掉 `if: !inputs.skip_fetch` 守卫——skip_fetch=true 时仍提交 projection
- `Deploy` 步骤始终执行（skip_fetch=true 时也部署）
- `git add` 覆盖 `site/public/maas-skill/`

### weekly-update.yml

- full/import 模式 Commit 前生成 site prebuild + public projection
- aggregate 模式不生成产物、不部署（只汇总素材）
- `git add` 覆盖 `site/public/maas-skill/`

### skip_fetch=true 语义（故障恢复路径）

修复前：skip_fetch=true 时 Commit/Deploy 被 `if: !skip_fetch` 跳过，无法用于恢复。

修复后：

```
skip_fetch=false: 抓取 + prebuild + projection + commit + deploy
skip_fetch=true:  不抓取，但使用当前 repo 数据 → prebuild + projection + commit + deploy
```

这非常适合故障恢复：不重新抓取外部站点，只把仓库里已有的新数据重新生成
projection 并发布。

### 不变

- `build-release.sh` tracked diff gate 保留（纯构建器，不自动 git add/commit）
- `deploy-release.sh` 不自动修改仓库
- daily health check 语义保留（价格抓取全部失败仍置红 run）
- Task 07 功能不 cherry-pick 到 main（独立修复分支）

## 回归测试

`tests/test_workflow_release_contract.py`（16 项），已加入 run-all-tests：

- T01/T01a: daily export + prebuild 在 commit 之前
- T02: export --check 在 export 之后、commit 之前
- T03: commit 包含 projection（git add data/）
- T04: deploy 在 commit 之后
- T05/T06: commit/export 不被 skip_fetch 守卫（恢复路径核心）
- T07: health check 在 deploy/verify 之后
- T08: deploy 不被 skip_fetch 守卫
- weekly: full/import export 在 commit 前；aggregate 不部署
- build-release/deploy-release 不自动 commit（纯构建器）
- 可重现 release：export 幂等（连续两次零写入，--check 通过）

## 恢复步骤

修复 merge main 后，推荐恢复方式：

```
daily-update workflow_dispatch
  skip_fetch=true
```

skip_fetch=true 会：
1. 不抓取外部站点
2. 用仓库已有数据（9-22）生成 projection + site prebuild
3. commit projection
4. deploy 精确 SHA
5. online verify

恢复后核对（必须一致）：

- Git main HEAD
- public manifest datasetVersion
- /api/v1/status datasetVersion
- production current release RID
- dataThrough

验证四入口：`/api/v1/status` `/api/v1/changes` `/api/v1/prices` `/feed.xml` `/maas-skill/`

## 区分两类失败

本次故障中，GitHub Action 红不等于抓取失败：

| 类型 | 原因 | 表现 |
|---|---|---|
| release failure | build-release tracked diff gate 拒载 | 数据已提交，projection 未发布 |
| health-check failure | fetch-prices 全部来源失败（exit 2） | 数据已提交部署，run 末尾置红 |

修复后两者分离：release failure 不会再发生（projection 在 commit 前生成）；
health-check failure 保留原语义（环境失效时置红）。

## Final Recovery / Closure

### 恢复过程

1. merge `fix/workflow-public-projection` → main（fast-forward，含 workflow 修复
   + workflow contract 测试 + incident 文档）
2. 首次触发 `daily-update skip_fetch=true` → 失败：`test_price_archive` 报
   `ModuleNotFoundError: No module named 'bs4'`（bs4 只在抓取步骤装，skip_fetch
   跳过抓取 → build-release tests 缺 bs4）
3. 修复：daily/weekly Setup Python 后新增 `Install Python dependencies`
   （`pip install -r requirements.txt`，始终执行）+ 测试 T09
4. 第二次触发 `daily-update skip_fetch=true` → 全绿，生产 activate 成功

### bs4 CI 依赖 bug（恢复过程额外发现）

根因：bs4 原来只在抓取步骤（Setup Playwright / Fetch pricing / Pricing
regression）装，这些步骤都有 `if: !skip_fetch`。skip_fetch=true 时
build-release run-all-tests 的 test_price_archive 需要 bs4 → ModuleNotFoundError。

修复：daily/weekly 在 Setup Python 后始终 `pip install -r requirements.txt`。

CI 设计约束（后续必须遵守）：**构建依赖必须在构建环境统一安装，不能靠前置
业务步骤"顺带装上"**——可跳过的业务步骤不应承载构建依赖。

### 最终对齐状态

| 维度 | 值 |
|---|---|
| Git main HEAD | `12692c595194c5f93a5fe5d0364f5062071bc218` |
| public manifest datasetVersion | `ds_0d06b42023365c32f6b79f0e98d730fef9af93b57865626e737307b4d5aafce5` |
| production /api/v1/status datasetVersion | `ds_0d06b42023365c32f6b79f0e98d730fef9af93b57865626e737307b4d5aafce5` |
| production current RID | `rl_12692c5951_0d06b4202336` |
| dataThrough | `2026-09-22` |
| coverage.changes.count | 4993 |
| coverage.prices.facts | 1411 |

### 四入口 online verify（全部 PASS）

| 入口 | HTTP |
|---|---|
| `/api/v1/status` | 200 |
| `/api/v1/changes` | 200 |
| `/api/v1/prices` | 200 |
| `/feed.xml` | 200 |
| `/maas-skill/SKILL.md` | 200 |

workflow Online verify 日志确认：REST /api/v1/status + REST /api/v1/changes +
MCP 工具调用 + RSS + Skill 四入口 datasetVersion 全部一致。

### Incident 状态：CLOSED

根因（workflow commit 前未生成 tracked 产物）已修复；skip_fetch=true 恢复路径
已经过真实生产验证；bs4 CI 依赖 bug 已修复；生产已恢复到 dataThrough 2026-09-22，
四者对齐，四入口 200。
