// Run from the repository root. Writes editorial drafts only; never publishes.
import { readFileSync, writeFileSync } from 'node:fs';
const observations = JSON.parse(readFileSync('site/src/data/daily_changes.json', 'utf8'));
const index = new Map(observations.days.flatMap(day => day.changed.map(c => [c.id, { ...c, date: day.date }])));
const ids = [
  'obs_3db8a4529be6c9c1a08d2fb870476b85a26ebbfe86f2607b04aa92dc515f2d0d',
  'obs_7ba0a774145370c258ee481336212b7c0da224b37edc87956cd4d20db03ce6f4',
  'obs_b430bb7e93094c95e3dcbaa684cab49865b04b24715f4529e84542f0661fa5d8',
];
const evidence = refs => refs.map(id => {
  const c = index.get(id);
  if (!c) throw new Error(`Missing archived observation: ${id}`);
  return { id, url: c.url, observedAt: c.date, note: '依据平台归档的官方来源差异。观察时间精度为日，未实时验证。' };
});
const base = {
  version: 1, models: [], families: [],
  period: { from: '2026-09-28T00:00:00+08:00', to: '2026-10-05T00:00:00+08:00' },
  dataThrough: '2026-10-03', coverage: 'partial',
  coverageNote: '截至10月3日的开发样例，统计周尚未结束；仅覆盖所引用的官方记录。',
  sample: false, correction: '', critical: false,
  limitations: '没有实际请求、账单或独立性能测试。只标厂商范围，不根据名称猜测模型归属。未覆盖对象不能认定为没有变化。',
};
const drafts = [
  {
    id: 'xai-transcription-lifecycle-20261003', kind: 'explainer', providers: ['xai'], topics: ['lifecycle', 'capability'],
    title: 'xAI转写：旧标识继续可用，不等于行为不变',
    preview: '归档说明旧标识将路由到新版本。需要检查实际路由与默认值，而不只是请求是否成功。',
    body: '观察事实：10月3日归档的官方日志说明1.0转写标识在10月2日进入生命周期终点，调用路由到2.0，默认版本说明也改为2.0。官方声称价格一致、准确率提高，平台没有独立验证。\n\n影响判断：请求成功不能证明旧模型仍在服务。依赖特定术语、格式或标点的验收，应在新路由上复验。\n\n建议动作：分别核对显式标识和默认调用；在接口提供时记录实际版本；使用获得授权的业务样本检查错误率、格式和耗时。这些是建议，平台未代用户执行。',
    conditions: '只针对来源明确提及的xAI Speech to Text转写标识；价格一致为官方声明，不推广到其他音频产品。',
    rows: [{ checkpoint: '旧标识', fact: '官方说明转路由', action: '核对真实服务行为' }, { checkpoint: '默认版本', fact: '文档改为2.0', action: '排查未显式指定版本的调用' }],
    evidence: evidence([ids[0]]),
  },
  {
    id: 'kimi-cache-conditions-20261002', kind: 'explainer', providers: ['kimi'], topics: ['billing', 'price'],
    title: 'Kimi缓存：命中价之外，先核对写入与TTL',
    preview: '缓存写入和命中需要分开记录。本次材料不足以计算涨跌百分比。',
    body: '观察事实：10月2日归档的Kimi定价说明描述K3缓存写入按TTL分别计费，默认使用短TTL，命中输入与写入费用分开说明，命中会延续有效期。\n\n影响判断：把缓存命中单价乘全部输入量，会遗漏写入成本。重复间隔和TTL会影响成本结构。\n\n建议动作：分列普通输入、缓存写入、命中和输出；核对实际TTL及重复间隔。参数不明时保留待确认，不补零。\n\n历史判断：页面新增说明不证明过去不收费。本条缺少同条件历史费率，不推断实际涨价，也不计算百分比。',
    conditions: '仅针对归档明确描述的Kimi K3缓存机制；不同模型、区域、币种、TTL分别核对。',
    rows: [{ item: '缓存写入', check: 'TTL与写入单价' }, { item: '缓存命中', check: '命中量和有效期' }, { item: '普通输入与输出', check: '同条件单价' }],
    evidence: evidence([ids[1]]),
  },
  {
    id: 'anthropic-retirement-20261001', kind: 'explainer', providers: ['anthropic'], topics: ['lifecycle', 'capability'],
    title: 'Claude API退休计划：把日期变成迁移检查',
    preview: '官方归档给出Sonnet 4.5的计划退休时间。迁移仍需核对平台和调用兼容性。',
    body: '观察事实：10月1日归档的官方日志宣布Sonnet 4.5弃用，Claude API计划在11月30日退休，并建议迁移至Sonnet 5.5。\n\n影响判断：该日期仅针对明确列出的Claude API，不能推断第三方托管平台同日停止，也不能把推荐版本视为已验证完全兼容。\n\n建议动作：定位旧标识配置和批处理任务；核对目的平台迁移指南；回归工具调用、输出格式与上下文策略。预留验证窗口，不把截止日当作开始迁移的日期。\n\n待确认：目标平台区域、配额和收费条件，本条未完成这些比较。',
    conditions: '生命周期日期和建议仅限该Claude API官方归档；后续修订以官方最新说明为准。',
    rows: [{ item: '退休日期', archived: '2026-11-30计划日期', check: '平台及后续修订' }, { item: '迁移建议', archived: 'Sonnet 5.5', check: '业务回归与条件' }],
    evidence: evidence([ids[2]]),
  },
  {
    id: 'lifecycle-comparison-20261003', kind: 'comparison', providers: ['xai', 'anthropic'], topics: ['lifecycle', 'capability'],
    title: '生命周期对照：自动路由与计划退休',
    preview: '两条官方记录体现不同处置机制。对照用于制定检查清单，不构成能力排名。',
    body: '比较方法：对照同一观察周的两条官方生命周期说明，比较接口处置方式。\n\nxAI旧转写标识转路由时，即使请求成功也应检查行为。Anthropic给出指定平台的未来退休计划时，需要在截止前完成迁移与回归。\n\n建议同时跟踪配置标识、实际行为与官方时间说明。只监控成功率会遗漏行为改变；只监控日期可能遗漏已经生效的切换。\n\n两个案例模态不同，不满足价格或性能比较条件，不输出百分比和性能排名。',
    conditions: '仅比较日志中的处置方式，不能比较不同模态产品的价格与准确率。',
    rows: [{ provider: 'xAI', policy: '旧标识转路由', focus: '实际服务行为' }, { provider: 'Anthropic', policy: '指定平台计划退休', focus: '日期与迁移完成度' }],
    evidence: evidence([ids[0], ids[2]]),
  },
  {
    id: 'cost-comparability-20261003', kind: 'comparison', providers: ['xai', 'kimi'], topics: ['price', 'billing'],
    title: '费用对照前：价格声明与计费条件不能混算',
    preview: '音频转写的价格一致声明与文本缓存的TTL说明，没有共同单位，不能算跨厂商价差。',
    body: '比较目的：展示条件核对步骤，不做最低价排名。\n\nxAI价格一致针对转写版本转路由；Kimi的TTL与写入说明针对文本缓存。计费对象不同，没有共同单位，不能计算跨厂商价差。\n\n实际费用对比前检查：模型和调用平台、模态、区域、币种、单位、输入输出、缓存写入与命中、TTL、上下文分档、生效时间。缺失字段保持未知。\n\n只有同条件、且旧值大于零，才输出变化百分比。官方价格相同不保证每种工作负载账单相同。',
    conditions: '对照信息完整性，不对照两个产品的实际成本高低。',
    rows: [{ dimension: '计费对象', xai: '音频转写', kimi: '文本缓存', comparable: '否' }, { dimension: '证据类型', xai: '价格一致声明', kimi: 'TTL与写入说明', comparable: '不能计算百分比' }],
    evidence: evidence([ids[0], ids[1]]),
  },
  {
    id: 'briefing-sample-20261003', kind: 'briefing', providers: ['xai', 'kimi', 'anthropic'], topics: ['price', 'billing', 'lifecycle', 'capability'], sample: true,
    title: '专业简报样例：生命周期与缓存计费的三项检查',
    preview: '完整结构样例：观察事实、影响、检查动作、条件与证据。统计周未结束，不是正式周报。',
    body: '本期为开发样例，截至10月3日，统计周尚未结束，覆盖为部分。\n\n一、xAI转写：归档说明旧标识转向新版本，建议核对旧标识和默认路径的业务验收。准确率提升属于官方声明，未独立验证。\n\n二、Kimi缓存：分开记录写入、命中与普通输入；核对TTL和重复间隔。缺少同条件旧费率，不输出涨跌百分比。\n\n三、Claude API：核对Sonnet 4.5依赖、实际托管平台及计划退休日期，安排调用兼容性回归。不能把第三方平台的日期视为相同。\n\n跨条目判断：配置标识、服务行为、计费条件和时间要同时记录。请求成功不代表行为未变，价格表不变不保证总账单相同。\n\n下一步建议：逐项核对业务依赖与缺失条件，关注后续官方修订。平台没有登录用户业务系统或执行上述检查。',
    conditions: '仅覆盖三条指定归档，10月3日至统计周结束尚未覆盖。',
    rows: [{ provider: 'xAI', action: '核对转写路由行为' }, { provider: 'Kimi', action: '拆分缓存成本项' }, { provider: 'Anthropic', action: '核对平台并安排迁移' }],
    evidence: evidence(ids),
  },
];
const labels={checkpoint:'检查点',fact:'观察',action:'建议动作',item:'项目',check:'待核对',archived:'归档说明',provider:'厂商',policy:'处置方式',focus:'检查重点',dimension:'对照项',xai:'xAI案例',kimi:'Kimi案例',comparable:'是否可比'};
for (const draft of drafts) draft.rows=draft.rows.map(row=>Object.fromEntries(Object.entries(row).map(([key,value])=>[labels[key]??key,value])));
for (const draft of drafts) writeFileSync(new URL(`./${draft.id}.json`, import.meta.url), JSON.stringify({ ...base, ...draft }, null, 2) + '\n');
