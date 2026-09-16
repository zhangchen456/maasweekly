# Task 02 盘点结论与固定契约（阶段 1 产出）

日期：2026-09-12。本文件是实施依据的事实记录，最终汇总进 task-02-result.md。

## 1. 现状核实（逐条对应任务书 §3）

| 任务书断言 | 核实结果 |
| --- | --- |
| Evidence 未持久化 | **属实**。fetch-prices.py L162 仅把 `evidence_id → snap.url` 存入 source_urls 供 ledger 的 source_url 字段；Evidence 对象（locator/excerpt/excerpt_hash）用后即弃。ledger_history 内的 evidence_id 是内存 ID（`ev-<sha256[:20]>` of snapshot_id:idx），无对应文件 |
| events_from_diff 固定 unit=per_1m_tokens | **属实**（L95/105）。当前八家全部 unit_quantity=1000000，所以历史事件未失真，但契约上错误 |
| 时间单位注释写 ms、实际秒 | **属实**。providers.py L73/L136 用 `time.time()`；extractors.py L2210 `observed_at=snapshot.fetched_at`；ledger_history 全部为秒（样例 1789081091 ≈ 2026-09-10T22:58Z）。**历史数据单位=秒，统一以秒为准，不按注释转换** |
| fact_to_dict 遗漏 effective_at | **属实**（view_data.py L35-60 无 effective_at 键）。当前八家 extractor 全部 `effective_at=None`，历史无损失，补键即可 |
| 历史基线跳过今天 | **属实**（latest_history L63 `p.stem != today`）。同日先成功后失败时，第二次沿用逻辑从 prev_history（=昨天）取 facts，可能回退 |
| 零事件不覆盖 price_changes | **属实**（write_price_changes L74-75 `if not changes: return`） |
| 每日快照同名覆盖 | **属实**。ledger_history/<date>.json 一天一份，无多版本能力 |
| excerpt 质量问题 | **部分属实**。HTML 路径：整表 HTML 片段（如 anthropic 8.5KB），可支撑核价；markdown 路径（extractors.py L493）：`" | ".join(rows[0])` 仅表头一行——**不满足 4.3 完整性**；Kimi 聚合页无子页定位 |

## 2. 数据盘点

- **ledger_history**：2026-09-06 ~ 09-12 共 7 天，2647 facts（qwen 2024 / doubao 268 / openai 140 / anthropic 85 / google 75 / glm 31 / deepseek 12 / kimi 12），evidence_id 去重 192 个，全部 confirmed、unit=(1000000, token)、effective_at 全空
- **渲染快照**：data/snapshots/2026-09-06..09-12 每日 8 个 `pricing__<provider>.html`（共 56 个，8.5MB/天），Kimi 为多子页拼接 HTML
- **回放验证**（迁移可行性）：2026-09-11 全部八家从快照 HTML 回放 extractor → normalize → 与当日 ledger_history 比对，**fact_key 集合与金额 100% 一致，零拒收**。即：现有快照足以重建证据链
- **daily_changes.price_changes**：09-08(22) / 09-09(5) / 09-10(3) / 09-11(12) / 09-12(2) 共 44 条，仅 provider/model/component/previous/current/currency/unit/changed_fields/evidence_url，无稳定 ID、无版本引用、无真实单位
- **Task 01 归档**：data/records 139 条 + record-revisions 139 目录，/item/[id].astro 仅渲染 obs_ 类型；周归档页取 weekly-digest ∪ record-index 并集路由

## 3. 固定契约（实施规则）

### 3.1 ID（前缀 + 完整 SHA-256，规范 JSON：UTF-8、ensure_ascii=False、键排序、紧凑分隔符）

| 对象 | 身份输入 | 前缀 |
| --- | --- | --- |
| 快照内容 | `[source_key, content_sha256]` | `psnap_` |
| 公开证据 | `[snapshot_content_id, locator_type, locator, excerpt_hash, extractor_version]` | `ev_`（与旧内存 ID `ev-` 区分） |
| 事实版本 | `[fact_key, amount, currency, unit_quantity, unit_name, region, billing_mode, service_tier, context_band, time_condition, effective_at, observed_at, evidence_id]` | `pfv_` |
| 每日事件 | `[fact_key, 上海日历日期]` | `price_` |

- 金额参与哈希前用 Decimal 规范化（`Decimal(amount).normalize()`），`1.0` 与 `1.00` 同一版本
- 哈希函数集中实现于 archive.py 单一处，禁止各入口自行拼接

### 3.2 时间

- 内部统一 **epoch 秒**（与现有 ledger_history 一致，不转换历史值）
- 新公开归档字段（evidence/fact version/price record 的 observedAt/revisedAt 等）用**含时区 ISO 8601**（UTC），转换只在 archive.py 序列化边界
- 上海日历日 = Asia/Shanghai 日期字符串；历史 ledger_history 文件名即该口径
- fact 版本内 observed_at 保留秒级浮点（与回放一致性兼容），公开页面显示日期精度

### 3.3 目录（与 obs_ 分离，不混用 Task 01 恢复器）

```
data/price-facts/versions/<pfv_id>.json        # 不可变事实版本
data/price-facts/current.json                  # fact_key → 最新已接受版本 ID（可重建）
data/price-evidence/<ev_id>.json               # 证据正文 + 快照元数据
data/price-snapshots/<psnap_id>.json           # 快照元数据（content 引用每日 HTML 文件，不复制正文）
data/price-runs/<date>/<run_id>.json           # 运行记录（prepared/committed 两态）
data/price-records/<price_id>.json             # 价格事件当前版
data/price-record-revisions/<price_id>/<rev>.json
site/src/data/price-record-index.json          # 可重建展示索引（事件）
site/src/data/price-evidence-index.json        # 可重建展示索引（证据）
```

- 快照正文不复制：psnap 元数据记 `content_ref`（仓库相对路径指向 data/snapshots/<date>/pricing__<provider>.html）+ sha256；content_ref 缺失（文件被清理）→ 证据标 partial(reasons 含 snapshot_missing)，摘录本身已存于 ev_ 文件不受影响
- 与 Task 01 的关联：source_key（如 `anthropic:pricing`）显式映射到 source_registry 的 pricing 信源，不假定 ID 相等

### 3.4 事件与基线

- 每日事件比较：**该上海日之前最后一个成功接受的版本** vs **该日最新成功接受版本**（两个状态独立持久：source 级 latest_success 用于失败沿用；date 基线用于日比较）
- changeType：amount_changed / terms_changed / newly_observed；币种单位变化 → terms_changed，不算涨跌
- 百分比仅当：模型/平台/组件/条件/币种/单位全同且旧值>0，`(新-旧)/旧*100`，Decimal 计算
- 旧值 0、条件变化、缺证 → 不输出百分比，列原因
- 零事件撤回规则与 Task 01 一致：来源成功+覆盖完整+明确重算无事件 → withdrawn 修订；来源失败/未执行/局部抽取不撤回
- `--only` 未运行来源：保留现有事件与状态，不标失败

### 3.5 证据完整性

- complete / partial / unavailable + reasons[]
- HTML 表证据（含表头+金额行）通常 complete；markdown 仅表头 → partial(reasons: excerpt_lacks_amount)；Kimi 聚合无法分辨子页 → partial(reasons: subpage_origin_unknown)；摘录被截断 → partial(reasons: truncated)
- 每条 fact 引用的证据必须能解释该金额（含条件）；同一表证据多 fact 复用合法
- 页面渲染：excerpt 为 HTML 时转安全纯文本表格（不执行 script/事件属性），非法 URL 协议不渲染外链

### 3.6 兼容与门禁

- ledger.json / ledger_history / daily_changes.price_changes 旧字段继续产出（llm-digest、模板、首页、周归档消费者不动）；新增字段叠加（id/permalink/unit_quantity/unit_name/version 引用）
- daily-update.yml 不改动执行顺序；fetch-prices.py 内部接入 archive
- validate-archive.py 保持 obs_ 契约不变；新增 price 校验走独立入口，npm prebuild 链式调用两者

## 4. 风险与边界决定

1. **快照正文依赖每日文件**：迁移期快照都在 data/snapshots/（git 跟踪），content_ref 稳定；不复制正文避免仓库翻倍（8.5MB/天 × 7 天）
2. **markdown 表头摘录**：现有 md 路径 excerpt 升级为完整表格文本（rows 全部拼接），extractor_version 不变（产出内容变化但 fixture 测试只断言证据链存在，需同步更新断言）
3. **2026-09-12 当天已跑过 fetch**：当日 price_changes 已存在（2 条 google），迁移重放以 ledger_history 已存事实为准，不重复产生事件
4. **qwen 2024 facts**：占 76%，事件索引按 (fact_key, date) 粒度不会爆炸（只有变化的事实产生事件）
