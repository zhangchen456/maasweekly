# DeepSeek API Pricing

> Fixture for offline adapter tests. Sanitized; not live data.
> Covers cache hit/miss and peak/off-peak time conditions (decision patch §1.1).

## deepseek-chat

| Model | Context window | Input (cache miss) | Output |
|-------|---------------|-------------------|--------|
| deepseek-chat | 128,000 | ¥0.27 / 1M tokens | ¥1.10 / 1M tokens |

### Cache hit

| Tier | Price |
|------|-------|
| Cache hit | ¥0.027 / 1M tokens |

### Time-based pricing (Asia/Shanghai)

| Period | Schedule | Input price |
|--------|----------|-------------|
| Peak | 00:00-08:00 | ¥0.27 / 1M tokens |
| Off-peak | 08:00-24:00 | ¥0.135 / 1M tokens |

Effective from 2026-08-01.
