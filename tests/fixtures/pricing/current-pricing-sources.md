# 2026-10-02 official pricing structure fixtures

These fixtures retain official DOM table fragments from a read-only browser capture.
Full unmodified source pages and observation timestamps are stored by the managed
pricing runs in `data/snapshots/content/` and `data/price-runs/`.

| Fixture | Official source | Regression |
| --- | --- | --- |
| openai_pricing_2026-10-02.html | https://developers.openai.com/api/docs/pricing | Short/long context; standard, batch, flex, fast, ultrafast; token unit in surrounding copy |
| anthropic_pricing_2026-10-02.html | https://platform.claude.com/docs/en/about-claude/pricing | Two header rows, expandable body group, model links with descriptions |
| google_pricing_2026-10-02.html | https://ai.google.dev/gemini-api/docs/pricing | Context bands, hourly cache storage separated from token reads, promotion expiry |
| kimi_pricing_2026-10-02.html | https://platform.kimi.com/docs/pricing/chat | Eight-column K3 vs six-column K2, 5m/1h cache writes |
| deepseek_pricing_2026-10-02.html | https://api-docs.deepseek.com/quick_start/pricing | Footnote removed from API model ID; UTC peak schedule |
| doubao_pricing_2026-10-02.html | https://www.volcengine.com/docs/82379/1544106 | Standard vs priority vs low-priority vs batch |

Fixtures preserve amounts and table semantics. Surrounding navigation and unrelated
model sections are omitted; they are not substitutes for the full archived evidence.
