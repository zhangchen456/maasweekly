# Vertex Claude / Arena source recovery

## Causes and official replacements

- Vertex Claude: the legacy generative-AI pricing URL redirects to the Google-model pricing page, which no longer contains Claude. Use `https://cloud.google.com/model-garden/partner-models/pricing` for `vertex-anthropic`. Keep the existing strict extractor and preserve blank cells as missing facts. The captured official regional tables yield 88 accepted facts across global, US and EU.
- LMArena: the former leaderboard moved to Arena and returns HTTP 403 from the production network, including the normal browser collector. Arena's [official dataset announcement](https://arena.ai/blog/arena-leaderboard-dataset) links the [official Hugging Face dataset](https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset), licensed CC BY 4.0. Use its complete latest Text Arena release and select only the `overall` category. Do not use historical GitHub mirrors or label this as coverage of other arenas.

## Integrity and freshness

The adapter pins the Hub revision, checks the expected single release shard, file size and LFS SHA256 before decoding. Bounded, streaming Parquet decoding and row validation reject empty, malformed, duplicate, mixed-date or future-dated results. Failure retains prior observations through the existing staged-fetch protocol; there is no fallback to a challenge page. The first change of transport establishes a baseline instead of reporting removals from incomparable HTML.

The initial production-network probe returned 419 overall records, published **2026-10-28**, from revision `323062f70843f40e3f739865c3fe9d806126e412`, file SHA256 `2f2b2d0891188311d704e27a5b68c386bb085bdc7f38f2890e806aa67d5b0dbb`. Collection time and publication date remain distinct. Publication revision, checksum, attribution, date and coverage are written into each normalized snapshot.

## Runtime and validation

`pyarrow==19.0.1` is added to the locked dependencies. Build and verify a candidate writer image before updating the server's writer-image pointer and canonical requirements under the existing release lock; preserve the previous pointer and requirements for rollback. No writer permissions, credentials or publication checks change.

Validation covers the real Vertex page fixture, official-file checksum and pinned URLs, streamed category selection, invalid rows, no HTML fallback, and migration without false model removals. Release through the normal code workflow, then run the normal `daily-update.yml` collection (`skip_fetch=false`) and verify the published dataset and both source states. A successful code deployment alone is not a recovered data source.
