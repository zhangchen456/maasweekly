export const priceGuidesEnglish = [
  {
    slug: 'token-cost', title: 'How to calculate LLM API costs: input tokens, output tokens and currency conversion',
    description: 'Calculate API costs from actual input and output tokens, understand per-million-token units, conversation history and agent calls, then check original quotes and billing conditions.',
    lead: 'Calculate input and output charges separately. A price per million tokens is a billing unit, not a fixed charge for every API request.',
    sections: [
      { title: 'Start with one request', paragraphs: [
        'For a text API that bills input and output separately, cost = input token count / input billing quantity × input unit price + output token count / output billing quantity × output unit price. For a per-million-token quote, divide by 1,000,000. For a per-thousand-token quote, divide by 1,000. Check the unit before applying the formula.',
        'Suppose input costs CNY 2 per million tokens and output costs CNY 8 per million tokens. A request with 10,000 input tokens and 2,000 output tokens costs 0.02 + 0.016 = CNY 0.036. Repeating the same workload 1,000 times costs CNY 36. These are teaching assumptions, not current quotes for any model.',
        'Tokens are not interchangeable with words, characters or Chinese characters. Tokenization differs between models. Use provider usage records when reconciling a bill. Image, audio, video and per-request charges have their own billing units and cannot automatically use this text-token formula.',
      ] },
      { title: 'Count the whole conversation or agent task', paragraphs: [
        'Input can include system instructions, the current question, retrieved passages, tool results and conversation history sent again. If each turn resends the complete history, input grows over the conversation. Add the actual usage of every request to calculate the total.',
        'One agent task can involve planning, tool selection, result processing, retries and a final answer. Estimate the entire task and multiply by task volume. Counting only the final answer misses intermediate requests. Reasoning and other output usage may also be billed; check the specific API definition.',
      ] },
      { title: 'Convert currencies after calculating the original charge', paragraphs: [
        'First calculate the charge in its original currency, then multiply by your exchange-rate assumption. A hypothetical USD 5 bill at CNY 7 per USD is CNY 35. That example rate is not live and excludes taxes, payment fees and top-up charges.',
        'The pricing workspace shows estimated conversions. Model pages retain original currencies, units and sources. Region, context length, batch versus realtime mode, time windows and service tiers must also match before comparing offers.',
      ] },
      { title: 'Use your own workload', paragraphs: [
        'Sample real tasks and record input, output, cache hits and the number of calls. Estimate typical and peak volumes separately. Until cache hits are verified, include a no-cache budget scenario.',
        'Select models and the relevant billing conditions in the pricing workspace, then enter usage. Open model details to check official sources, observation times and update status. An estimate can differ from the final provider bill.',
      ] },
    ],
    links: [{ href: '/pricing/#api-pricing', label: 'Open API prices and the usage calculator' }, { href: '/models/', label: 'Find original model quotes' }, { href: '/guides/prompt-caching/', label: 'Understand cache charges' }],
    sources: [{ href: '/method/', label: 'Data method and billing conditions' }],
  },
  {
    slug: 'prompt-caching', title: 'LLM prompt caching costs: cache reads, writes and hit rates',
    description: 'Estimate prompt caching costs from actual hits, cache-read and cache-write prices. Avoid counting input tokens twice and check provider-specific billing rules.',
    lead: 'Savings depend on actual cache hits, read prices, write charges and retention. Do not apply the cache-read price to every input token.',
    sections: [
      { title: 'Separate ordinary input, cache reads and cache writes', paragraphs: [
        'These usage categories can have different unit prices. A provider may cache automatically or require explicit cache creation. It may also charge for storage time. A missing cache-write quote does not establish that writes are free.',
        'Read the usage-field definitions carefully. Cached tokens may be a subset of total input tokens. If total input includes hits, subtract those hits before calculating ordinary input charges. Do not charge the same tokens as both ordinary input and cache reads.',
      ] },
      { title: 'Work through a cache-hit example', paragraphs: [
        'Assume total input is 10,000 tokens, including 8,000 cache-hit tokens. If ordinary input costs CNY 2 per million and cache reads cost CNY 0.2 per million, the input charge is 2,000 / 1,000,000 × 2 + 8,000 / 1,000,000 × 0.2 = CNY 0.0056. With no cache hits, input would cost CNY 0.02.',
        'This is a hypothetical read-cost example, not a model quote. Output, initial writes, storage and rebuilding expired caches must be calculated separately. Apply the hit price only when actual provider usage identifies the cached portion.',
      ] },
      { title: 'Similar questions do not guarantee a hit', paragraphs: [
        'Cache rules can depend on matching prefixes, minimum token counts, model versions, retention times and request formats. Semantic similarity does not necessarily mean a prefix is reusable. Changing instructions or context can change matching behavior. Check the official API documentation.',
        'Observe hit rates and charges with your real workload. Repeated, stable context is useful for testing. Do not remove information that needs to be updated just to increase hits; verify that responses remain correct.',
      ] },
      { title: 'Include the cost of establishing and retaining the cache', paragraphs: [
        'Compare the cost of the same workload without caching against uncached input + cache reads + writes + storage + output. Repeated-read savings must exceed the incremental cost of establishing and retaining the cache before there is a cost benefit.',
        'If you do not know the actual hit rate, calculate both zero-hit and expected-hit scenarios. Model detail pages show observed billing items and conditions. Return to official documentation when an item is missing instead of assuming a zero price.',
      ] },
    ],
    links: [{ href: '/models/', label: 'Inspect input, output and cache quotes' }, { href: '/guides/token-cost/', label: 'Calculate the complete API charge' }, { href: '/pricing/#api-pricing', label: 'Compare costs for your workload' }],
    sources: [{ href: '/method/', label: 'Quote fields, evidence and missing data' }, { href: 'https://platform.claude.com/docs/en/build-with-claude/prompt-caching', label: 'Claude official prompt caching documentation' }, { href: 'https://ai.google.dev/gemini-api/docs/caching', label: 'Gemini official context caching documentation' }],
  },
  {
    slug: 'compare-api-prices', title: 'How to compare the same LLM API across providers and billing conditions',
    description: 'Check upstream model identity, region, context length, caching, batch modes and time windows before comparing API costs. Follow a practical process with linked quote evidence.',
    lead: 'Confirm the same model and service conditions before comparing charges. Similar names or a lower listed price do not establish that two APIs are interchangeable.',
    sections: [
      { title: 'Confirm model identity and the serving platform', paragraphs: [
        'A model developer and an API serving platform are different entities. Several platforms can serve the same upstream model. Aliases, snapshots and fine-tuned versions may differ. Check official relationships and API identifiers before treating offers as the same model.',
        'Our cross-platform page lists verified relationships, developers, platforms, API names and relationship evidence. A listed relationship does not verify registration, payment or actual calls. It also does not imply that every platform has a complete quote.',
      ] },
      { title: 'Align the billing conditions', paragraphs: [
        'Check original currency and units, then region, context length, realtime or batch mode, standard or priority tiers, cache reads and writes, and time windows. A long-context tier or promotional offer cannot simply replace another platform’s standard realtime price.',
        'Use the same input and output workload. If platform A has cheaper input but more expensive output than platform B, long-input/short-output and short-input/long-output tasks can produce different cost conclusions. This illustrates the method, not an actual provider comparison.',
      ] },
      { title: 'Check freshness and complete evidence', paragraphs: [
        'Inspect observation times, collection status and official pricing links. Treat retained older quotes after an update failure separately. Without complete input and output prices, the total cost of the same task cannot be compared reliably. Missing quotes do not mean free service.',
        'Change records track history; current quote pages show recently accepted observations. Observation time can differ from a price’s effective time. Resolve conflicts using official conditions and effective-date notices before setting a business budget.',
      ] },
      { title: 'Validate with a real workload', paragraphs: [
        'Costs are only one consideration. Validate context limits, tool calling, structured output, latency, stability, rate limits and data-handling requirements. Sharing an upstream model does not guarantee identical service behavior or features.',
        'Check model relationships and prices on the comparison page, inspect all tiers on model details, then compare your usage in the workspace. Save the quote, conditions and observation time so that you can recalculate after changes.',
      ] },
    ],
    links: [{ href: '/compare/', label: 'Inspect verified cross-platform quotes' }, { href: '/pricing/#api-pricing', label: 'Compare the same usage across models' }, { href: '/changes/', label: 'Follow price and platform changes' }],
    sources: [{ href: '/method/', label: 'Model identity, quote evidence and comparison method' }],
  },
];
