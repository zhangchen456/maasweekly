# OpenAI API Pricing

> Fixture for offline adapter tests. Sanitized; not live data.
> This is a Markdown approximation of the OpenAI pricing page structure.

## GPT-5

| Model | Context window | Input | Output |
|-------|---------------|-------|--------|
| GPT-5 | 400,000 | $1.25 / 1M tokens | $10.00 / 1M tokens |

### Cached input

| Tier | Price |
|------|-------|
| Cache read | $0.125 / 1M tokens |
| Cache write (5m) | $1.25 / 1M tokens |

### Batch

| Mode | Input | Output |
|------|-------|--------|
| Batch | $0.625 / 1M tokens | $5.00 / 1M tokens |

### Long context

| Input length | Input price |
|-------------|-------------|
| 0–272,000 tokens | $1.25 / 1M tokens |
| 272,001+ tokens | $2.50 / 1M tokens |

## o3

| Model | Context window | Input | Output |
|-------|---------------|-------|--------|
| o3 | 200,000 | $2.00 / 1M tokens | $8.00 / 1M tokens |
