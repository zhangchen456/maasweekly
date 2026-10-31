import { formatTimestamp } from '../../public/time-display.js';
import {recordWorkspaceResult} from './workspace-analytics';
import {readCalculation,calculationLink} from '../lib/workspace-share';
import { savedState,currentAccount,openAccountLogin,onAccountChange,flushAccountState,accountApi,refreshAccount } from './account-client';
import type { WorkspaceData, LedgerPrice, WorkspaceModel, PriceVariant, SourceCondition } from '../lib/pricing-workspace';
interface WorkspaceElements {
    'display-currency': HTMLSelectElement;
    'currency-shortcut': HTMLButtonElement;
    'updated': HTMLElement;
    'theme': HTMLButtonElement;
    'stats': HTMLElement;
    'hero-chart': HTMLElement;
    'notice': HTMLElement;
    'compare-shortcut': HTMLButtonElement;
    'providers': HTMLElement;
    'provider-title': HTMLElement;
    'provider-subtitle': HTMLElement;
    'search': HTMLInputElement;
    'model-filter': HTMLSelectElement;
    'family-filter': HTMLSelectElement;
    'sort': HTMLSelectElement;
    'filter-summary': HTMLElement;
    'filter-error': HTMLElement;
    'models': HTMLElement;
    'catalog-empty': HTMLElement;
    'page-label': HTMLElement;
    'prev': HTMLButtonElement;
    'next': HTMLButtonElement;
    'compare': HTMLElement;
    'clear': HTMLButtonElement;
    'input-value': HTMLElement;
    'input-volume': HTMLInputElement;
    'output-value': HTMLElement;
    'output-volume': HTMLInputElement;
    'selection': HTMLElement;
    'components': HTMLElement;
    'chart-unit': HTMLElement;
    'plot': HTMLElement;
    'legend-input': HTMLElement;
    'legend-output': HTMLElement;
    'comparison-table': HTMLElement;
    'comparison-note': HTMLElement;
    'fx-settings': HTMLElement;
    'fx': HTMLInputElement;
    'fx-label': HTMLElement;
    'footer-meta': HTMLElement;
    'toast': HTMLElement;
    'detail': HTMLDialogElement;
    'detail-title': HTMLElement;
    'close-detail': HTMLButtonElement;
    'facts': HTMLElement;
    'goal-data': HTMLScriptElement;
    'price-ledger': HTMLElement;
}
export function startPriceWorkspace() {
    const root = document.getElementById('price-ledger');
    if (!root || root.dataset.initialized === 'true')
        return;
    root.dataset.initialized = 'true';
    const $ = <K extends keyof WorkspaceElements>(id: K): WorkspaceElements[K] => { const element = document.getElementById(id); if (!element)
        throw new Error('Missing price control: ' + id); return element as WorkspaceElements[K]; };
    const data: WorkspaceData = JSON.parse($('goal-data').textContent ?? '{}');
    const rows = Array.isArray(data.prices) ? data.prices : [];
    const en = document.documentElement.lang === 'en';
    const defaultCurrency = en ? 'USD' : 'CNY';
    let currency: 'USD' | 'CNY' = defaultCurrency;
    let currencyExplicit = false;
    const symbol = () => currency === 'USD' ? 'US$' : '¥';
    const money = (n: number | null) => n === null ? (en ? 'Not available' : '暂无') : symbol() + fmt(n);
    const brands: Record<string, string[]> = { 'vertex-google': ['Google Cloud / Gemini', 'Gemini', 'G'], 'vertex-anthropic': ['Google Cloud / Claude', 'Claude', 'G'], openai: ['OpenAI', 'OpenAI', 'O'], anthropic: ['Anthropic', 'Claude', 'A'], google: ['Google', 'Gemini', 'G'], deepseek: ['DeepSeek', '深度求索', 'D'], qwen: ['通义千问', 'Qwen', 'Q'], glm: ['智谱', 'GLM', 'Z'], kimi: ['Kimi', '月之暗面', 'K'], doubao: ['豆包', '火山引擎', '豆'] };
    function providerMark(p: string) { const wrap = el('span', 'monogram'), src = data.provider_logos?.[p], fallback = brands[p]?.[2] || p.slice(0, 1); if (!src) {
        wrap.textContent = fallback;
        return wrap;
    } const img = el('img', 'provider-logo'); img.alt = ''; img.loading = 'lazy'; img.src = src; img.onerror = () => { wrap.textContent = fallback; }; wrap.append(img); return wrap; }
    const componentNames: Record<string, string> = { input: '输入', output: '输出', cache_read: '缓存读取', cache_write: '缓存写入' };
    const order = ['openai', 'anthropic', 'google', 'deepseek', 'qwen', 'glm', 'kimi', 'doubao'];
    function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: unknown): HTMLElementTagNameMap[K] { const x = document.createElement(tag); if (cls)
        x.className = cls; if (text !== undefined)
        x.textContent = String(text); return x; }
    function append<T extends HTMLElement>(parent: T, ...children: (Node | string)[]): T { parent.append(...children); return parent; }
    function name(p: string) { return brands[p]?.[0] || p; }
    function num(v: unknown): number | null { if (v === null || v === undefined || v === '')
        return null; const n = Number(v); return Number.isFinite(n) && n >= 0 ? n : null; }
    function fmt(n: number | null) { return n === null ? '暂无' : n === 0 ? '0' : n < .01 ? n.toLocaleString('zh-CN', { maximumSignificantDigits: 3 }) : n.toLocaleString('zh-CN', { maximumFractionDigits: n < 1 ? 4 : 2 }); }
    function date(v: number | string | undefined) { return !v ? '未记录' : formatTimestamp(typeof v === 'number' ? v * 1000 : v, { locale: document.documentElement.lang === 'en' ? 'en-US' : 'zh-CN' }); }
    function parse(v: SourceCondition): SourceCondition { if (!v)
        return null; if (typeof v === 'object')
        return v; try {
        return JSON.parse(v) as SourceCondition;
    }
    catch {
        return v;
    } }
    function stable(v: SourceCondition) { v = parse(v); return v && typeof v === 'object' ? JSON.stringify(Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]]))) : String(v || ''); }
    let fx = 7, fxManual = true;
    const snap = data.fx_snapshot || {};
    // Snapshot rates are units of the target currency per one base currency.
    const rate = snap.base === 'USD' ? Number(snap.rates?.CNY) : snap.base === 'CNY' ? 1 / Number(snap.rates?.USD) : NaN;
    if (Number.isFinite(rate) && rate >= .01 && rate <= 1000) {
        fx = rate;
        fxManual = false;
    }
    $('fx').value = String(fx);
    function updateFxLabel() {
        $('currency-shortcut').textContent = currency + ' · ' + (en ? 'FX ' : '汇率 ') + fmt(fx);
        $('display-currency').value = currency;
        document.getElementById('hero-currency')!.textContent = currency + (en ? ' · estimate' : ' · 估算');
        document.getElementById('catalog-currency')!.textContent = en ? `Browse quote sources and add models to compare. Units: ${currency} per million tokens.` : `按报价来源浏览，选择模型加入下方对比。价格单位：${currency} / 百万 tokens。`;
        const asOf = snap.as_of || snap.effective_at;
        $('fx-label').textContent = fxManual ? (en ? 'Manual estimate · not a live exchange rate' : '手动估算 · 非实时汇率') : (en ? 'Reference estimate · not a live exchange rate' : '基准估算 · 非实时汇率') + (asOf ? ' · ' + date(asOf) : '');
    }
    updateFxLabel();
    function displayedAmount(r: LedgerPrice | undefined) { if (!r || !['token', 'tokens'].includes(r.unit_name))
        return null; const n = num(r.amount_per_1m); if (n === null)
        return null; if (r.currency === currency)
        return n; if (r.currency === 'CNY')
        return n / fx; if (r.currency === 'USD')
        return n * fx; const converted = num(r.converted_amount_per_1m); if(converted === null)return null; return r.converted_currency === currency ? converted : r.converted_currency === 'CNY' && currency === 'USD' ? converted / fx : r.converted_currency === 'USD' && currency === 'CNY' ? converted * fx : null; }
    function condition(r: LedgerPrice) { const c = parse(r.context_band), t = parse(r.time_condition); const parts = [r.region === 'cn' ? '中国大陆' : r.region === 'global' ? '全球' : r.region || '区域未标注']; if (c) {
        parts.push(typeof c === 'object' ? `${c.min_input_tokens ?? 0}–${c.max_input_tokens ?? '不限'} 输入 tokens` : String(c));
    }
    else
        parts.push('上下文未分档'); if (t)
        parts.push(String(typeof t === 'object' ? (({ peak: '高峰时段', off_peak: '低峰时段' } as Record<string,string>)[String(t.period)] || t.schedule || JSON.stringify(t)) + `（${t.tz || '来源时区未注明'}）` : String(t))); if (r.billing_mode && r.billing_mode !== 'realtime')
        parts.push(r.billing_mode); if (r.service_tier && r.service_tier !== 'standard')
        parts.push(r.service_tier); return parts.join(' · '); }
    const map = new Map<string, WorkspaceModel>();
    for (const r of rows) {
        const key = JSON.stringify([r.provider, r.model]);
        if (!map.has(key))
            map.set(key, { key, provider: r.provider, model: r.model, name: r.model_display_name || r.model, modelId: r.modelId || null, modelName: r.modelName || null, familyId: r.familyId || null, familyName: r.familyName || null, variants: new Map(), options: [], variant: 0 });
        const m = map.get(key)!;
        const vk = JSON.stringify([r.region, r.billing_mode, r.service_tier, stable(r.context_band), stable(r.time_condition)]);
        if (!m.variants.has(vk))
            m.variants.set(vk, { key: vk, label: condition(r), rows: [] });
        m.variants.get(vk)!.rows.push(r);
    }
    const models = [...map.values()].sort((a, b) => a.name.localeCompare(b.name));
    for (const m of models) {
        m.options = [...m.variants.values()].sort((a, b) => { const score = (v: PriceVariant) => { const t=parse(v.rows[0].time_condition), c=parse(v.rows[0].context_band); return (t && typeof t === 'object' && t.period === 'off_peak' ? 10 : 0) + (c && typeof c === 'object' ? Number(c.min_input_tokens || 0) : 0); }; return score(a) - score(b) || a.label.localeCompare(b.label); });
        m.variant = 0;
    }
    const providers = [...new Set(models.map(m => m.provider))].sort((a, b) => { const rank = (p: string) => order.includes(p) ? order.indexOf(p) : 100; return rank(a) - rank(b) || a.localeCompare(b); });
    let provider = providers[0] || '', query = '', page = 0, sort = 'name', component = 'total', input = 1, output = .25;
    const selected = new Set<string>();
    for (const p of ['openai', 'anthropic', 'deepseek']) {
        const m = models.find(m => m.provider === p);
        if (m)
            selected.add(m.key);
    }
    // T07-4A：model/family selector + URL 状态（modelId/familyId 互斥）
    const catalog = data.modelIdentities || { models: [], families: [] };
    const catalogModels = [...catalog.models].sort((a, b) => (a.modelName || '').localeCompare(b.modelName || ''));
    const catalogFamilies = [...catalog.families].sort((a, b) => (a.familyName || '').localeCompare(b.familyName || ''));
    let modelIdFilter: string | null = null, familyIdFilter: string | null = null;
    let filterError: {type: string; value: string} | null = null;
    function parseUrlFilter() { const u = new URL(location.href); const mid = u.searchParams.get('modelId'), fid = u.searchParams.get('familyId'); modelIdFilter = null; familyIdFilter = null; filterError = null; if (mid) {
        if (catalogModels.some(m => m.modelId === mid))
            modelIdFilter = mid;
        else
            filterError = { type: 'modelId', value: mid };
    }
    else if (fid) {
        if (catalogFamilies.some(f => f.familyId === fid))
            familyIdFilter = fid;
        else
            filterError = { type: 'familyId', value: fid };
    } }
    function syncUrlState() { const u = new URL(location.href); u.searchParams.delete('modelId'); u.searchParams.delete('familyId'); if (modelIdFilter)
        u.searchParams.set('modelId', modelIdFilter); if (familyIdFilter)
        u.searchParams.set('familyId', familyIdFilter); history.pushState(null, '', u); }
    function initSelectors() { const mf = $('model-filter'), ff = $('family-filter'); mf.innerHTML = '<option value="">模型</option>'; catalogModels.forEach(m => { const o = el('option', '', m.modelName); o.value = m.modelId; mf.append(o); }); ff.innerHTML = '<option value="">模型系列</option>'; catalogFamilies.forEach(f => { const o = el('option', '', f.familyName); o.value = f.familyId; ff.append(o); }); mf.value = modelIdFilter || ''; ff.value = familyIdFilter || ''; }
    function renderFilterError() { const fe = $('filter-error'); if (!filterError) {
        fe.hidden = true;
        fe.replaceChildren();
        return;
    } fe.hidden = false; fe.replaceChildren(); const p = el('p', '', '未找到模型：' + filterError.value + '。该 ID 不在当前模型目录中。'); const btn = el('button', '', '清除筛选'); btn.setAttribute('type', 'button'); btn.onclick = () => { filterError = null; syncUrlState(); initSelectors(); renderProviders(); renderCatalog(); renderFilterSummary(); renderFilterError(); }; const row = el('div', 'row'); row.append(p, btn); fe.append(row); }
    function facts(m: WorkspaceModel, c: string) { return m.options[m.variant].rows.filter(r => r.component === c); }
    function amount(m: WorkspaceModel, c: string): number | null { const rs = facts(m, c); const values = rs.map(displayedAmount).filter(n => n !== null); if (!values.length)
        return null; const distinct = [...new Set(values)]; return distinct.length === 1 ? distinct[0] : null; }
    function priceRange(m: WorkspaceModel, c: string) { const rs = facts(m, c); const values = rs.map(displayedAmount).filter(n => n !== null); const distinct = [...new Set(values)]; return distinct.length > 1 ? [Math.min(...distinct), Math.max(...distinct)] : null; }
    ;
    function stale(m: WorkspaceModel) { return m.options[m.variant].rows.some(r => r.field_state !== 'confirmed'); }
    function cost(m: WorkspaceModel, i = input, o = output) { const a = amount(m, 'input'), b = amount(m, 'output'); return i > 0 && a === null || o > 0 && b === null ? null : (a || 0) * i + (b || 0) * o; }
    function metric(m: WorkspaceModel) { return component === 'total' ? cost(m) : amount(m, component); }
    function selectedModels() { return [...selected].map(k => map.get(k)).filter((m): m is WorkspaceModel => Boolean(m)); }
    let toastTimer: ReturnType<typeof setTimeout> | undefined;
    function toast(s: string) { $('toast').textContent = s; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').textContent = '', 3000); }
    function toggle(m: WorkspaceModel) { if (selected.has(m.key))
        selected.delete(m.key);
    else if (selected.size === 5) {
        toast('最多对比 5 个模型，请先移除一个。');
        return;
    }
    else
        selected.add(m.key); renderCatalog(); renderCompare(); renderHero(); if(selectedModels().filter(m=>metric(m)!==null).length>=2)recordWorkspaceResult('comparison_completed'); }
    function renderProviders() { $('providers').replaceChildren(); for (const p of providers) {
        const count = models.filter(m => m.provider === p).length;
        const b = el('button', 'provider' + (p === provider && !query ? ' active' : ''));
        b.setAttribute('aria-pressed', String(p === provider && !query));
        append(b, providerMark(p), append(el('div'), el('b', '', name(p)), el('small', '', brands[p]?.[1] || p)), el('span', 'count', count));
        b.onclick = () => { provider = p; query = ''; $('search').value = ''; page = 0; renderProviders(); renderCatalog(); };
        $('providers').append(b);
    } }
    function cellPrice(m: WorkspaceModel, c: string) { const td = el('td'), v = amount(m, c), rg = priceRange(m, c); const price = el('span', 'price'); if (v !== null)
        price.append(el('em', '', symbol())); price.append(document.createTextNode(fmt(v))); if (rg)
        price.append(el('em', '', ' 起')); td.append(price); if (rg)
        td.append(el('small', 'model-note', '该条件下 ' + facts(m, c).length + ' 档报价 ' + fmt(rg[0]) + '–' + fmt(rg[1]) + ' · 详情见报价来源')); return td; }
    function renderCatalog() { if (filterError) {
        $('models').replaceChildren();
        $('catalog-empty').hidden = true;
        $('page-label').textContent = '';
        $('provider-title').textContent = '';
        $('provider-subtitle').textContent = '';
        $('prev').disabled = true;
        $('next').disabled = true;
        return;
    } let list; if (modelIdFilter)
        list = models.filter(m => m.modelId === modelIdFilter);
    else if (familyIdFilter)
        list = models.filter(m => m.familyId === familyIdFilter);
    else
        list = models.filter(m => query ? (m.name + ' ' + m.model + ' ' + name(m.provider)).toLowerCase().includes(query.toLowerCase()) : m.provider === provider); if (sort !== 'name')
        list.sort((a, b) => (amount(a, sort) ?? Infinity) - (amount(b, sort) ?? Infinity) || a.name.localeCompare(b.name)); page = Math.max(0, Math.min(page, Math.ceil(list.length / 6) - 1)); const titlePrefix = modelIdFilter ? catalogModels.find(m => m.modelId === modelIdFilter)?.modelName || modelIdFilter : familyIdFilter ? catalogFamilies.find(f => f.familyId === familyIdFilter)?.familyName + ' 系列' : query ? '全部厂商 · 搜索结果' : name(provider); $('provider-title').textContent = titlePrefix; $('provider-subtitle').textContent = `${list.length} 个模型 · 同条件分组件报价`; $('models').replaceChildren(); for (const m of list.slice(page * 6, page * 6 + 6)) {
        const tr = el('tr'), td = el('td');
        const nameWrap = el('div', 'model-name');
        nameWrap.append(el('span', '', m.name));
        if (m.modelId) {
            const tag = el('button', 'model-tag', m.modelName || m.name);
            tag.setAttribute('aria-label', '筛选模型 ' + (m.modelName || m.name));
            tag.setAttribute('type', 'button');
            tag.setAttribute('data-analytics-model-id', m.modelId);
            tag.onclick = () => { modelIdFilter = m.modelId; familyIdFilter = null; filterError = null; syncUrlState(); initSelectors(); renderProviders(); renderCatalog(); renderFilterSummary(); renderFilterError(); };
            nameWrap.append(tag);
            if (m.familyId && m.familyName) {
                const ftag = el('button', 'family-tag', m.familyName);
                ftag.setAttribute('aria-label', '筛选系列 ' + m.familyName);
                ftag.setAttribute('type', 'button');
                ftag.onclick = () => { familyIdFilter = m.familyId; modelIdFilter = null; filterError = null; syncUrlState(); initSelectors(); renderProviders(); renderCatalog(); renderFilterSummary(); renderFilterError(); };
                nameWrap.append(ftag);
            }
            else if (m.familyId) {
                const ftag = el('button', 'family-tag', m.familyName || '系列');
                ftag.setAttribute('type', 'button');
                ftag.disabled = true;
                nameWrap.append(ftag);
            }
        }
        else if (m.model) {
            td.append(el('span', 'model-note', m.model));
        }
        td.append(nameWrap);
        if (m.options.length > 1) {
            const sel = el('select');
            sel.setAttribute('aria-label', m.name + '计费条件');
            sel.style.cssText = 'width:100%;font-size:10px;padding:3px 5px;margin-top:6px';
            m.options.forEach((v, i) => { const op = el('option', '', v.label); op.value = String(i); sel.append(op); });
            sel.value = String(m.variant);
            sel.onchange = () => { m.variant = Number(sel.value); renderCatalog(); renderCompare(); renderHero(); };
            td.append(sel);
        }
        else
            td.append(el('span', 'model-note', m.options[0].label));
        const details = el('button', 'details-btn', (stale(m) ? '旧数据 · ' : '') + '报价与来源 ↗');
        details.onclick = () => showDetails(m);
        td.append(details);
        tr.append(td, cellPrice(m, 'input'), cellPrice(m, 'output'), cellPrice(m, 'cache_read'));
        const action = el('button', 'add' + (selected.has(m.key) ? ' selected' : ''), selected.has(m.key) ? '✓ 已加入' : '+ 对比');
        action.setAttribute('aria-label', (selected.has(m.key) ? '移除 ' : '对比 ') + m.name);
        action.setAttribute('aria-pressed', String(selected.has(m.key)));
        action.onclick = () => toggle(m);
        tr.append(append(el('td'), action));
        $('models').append(tr);
    } $('catalog-empty').hidden = list.length > 0; $('page-label').textContent = list.length ? `${page * 6 + 1}–${Math.min(page * 6 + 6, list.length)} / ${list.length} 个模型` : '0 个模型'; $('prev').disabled = page === 0; $('next').disabled = (page + 1) * 6 >= list.length; }
    function renderFilterSummary() { const fs = $('filter-summary'); fs.replaceChildren(); fs.hidden = true; if (modelIdFilter) {
        const chip = el('span', 'filter-chip');
        chip.append(el('span', '', '模型：' + (catalogModels.find(m => m.modelId === modelIdFilter)?.modelName || modelIdFilter)));
        const x = el('button', '', '×');
        x.setAttribute('aria-label', '清除模型筛选');
        x.onclick = () => { modelIdFilter = null; filterError = null; syncUrlState(); initSelectors(); renderProviders(); renderCatalog(); renderFilterSummary(); renderFilterError(); };
        chip.append(x);
        fs.append(chip);
        fs.hidden = false;
    }
    else if (familyIdFilter) {
        const chip = el('span', 'filter-chip');
        chip.append(el('span', '', '模型系列：' + (catalogFamilies.find(f => f.familyId === familyIdFilter)?.familyName || familyIdFilter)));
        const x = el('button', '', '×');
        x.setAttribute('aria-label', '清除系列筛选');
        x.onclick = () => { familyIdFilter = null; filterError = null; syncUrlState(); initSelectors(); renderProviders(); renderCatalog(); renderFilterSummary(); renderFilterError(); };
        chip.append(x);
        fs.append(chip);
        fs.hidden = false;
    } }
    function renderHero() { $('hero-chart').replaceChildren(); const ms = selectedModels().slice(0, 3), max = Math.max(...ms.map(m => cost(m, 1, .25) || 0), 1); if (!ms.length) {
        $('hero-chart').append(el('p', 'small muted', '选择模型后，这里会呈现成本差异。'));
        return;
    } for (const m of ms) {
        const n = cost(m, 1, .25), row = el('div', 'mini-row');
        const label = el('span', '', m.name);
        label.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
        label.title = m.name;
        const fill = el('div', 'mini-fill');
        fill.style.width = (n === null ? 0 : n / max * 100) + '%';
        append(row, label, append(el('div', 'mini-track'), fill), el('b', 'number', money(n)));
        $('hero-chart').append(row);
    } }
    function renderCompare() { const ms = selectedModels(); $('chart-unit').textContent = currency + (component === 'total' ? (en ? ' / selected usage' : ' / 当前用量') : (en ? ' / million tokens' : ' / 百万 tokens')); $('compare-shortcut').textContent = '对比 ' + ms.length + ' / 5 ↓'; $('selection').replaceChildren(); for (const m of ms) {
        const b = append(el('button', '', m.name), el('span', '', '×'));
        b.setAttribute('aria-label', '从对比移除 ' + m.name);
        b.onclick = () => toggle(m);
        $('selection').append(b);
    } $('plot').replaceChildren(); $('comparison-table').replaceChildren(); $('comparison-note').textContent = ms.some(stale) ? '含旧数据，请结合模型详情中的采集日期与来源核对。' : '各模型采用上方选定的计费条件；不同区域、上下文和时段可能影响价格。'; if (ms.length < 1) {
        $('plot').append(el('div', 'empty', ms.length ? '再加入 1 个模型，即可开始对比。' : en ? 'Add 1–5 models from the catalog to estimate costs.' : '在模型目录中加入 1–5 个模型，开始计算。'));
        return;
    } const max = Math.max(...ms.map(m => metric(m) || 0), .01); for (const m of ms) {
        const n = metric(m);
        const row = el('div', 'plot-row'), label = append(el('div', 'plot-label', m.name), el('small', '', name(m.provider) + (stale(m) ? ' · 旧数据' : '')));
        const track = el('div', 'track');
        track.setAttribute('aria-label', m.name + ' ' + (n === null ? '暂无可比报价' : currency + ' ' + fmt(n)));
        if (n !== null) {
            const a = el('div', 'bar input-bar'), b = el('div', 'bar output-bar');
            a.style.width = ((component === 'total' ? (amount(m, 'input') || 0) * input : n) / max * 100) + '%';
            b.style.width = (component === 'total' ? (amount(m, 'output') || 0) * output / max * 100 : 0) + '%';
            track.append(a, b);
        }
        row.append(label, track, el('div', 'plot-price number', money(n)));
        $('plot').append(row);
    } const head = el('thead'), hr = append(el('tr'), el('th', '', '价格 / 条件')); ms.forEach(m => hr.append(el('th', '', m.name))); head.append(hr); const body = el('tbody'); for (const c of ['input', 'output', 'cache_read', 'cache_write', 'total', 'condition']) {
        const tr = append(el('tr'), el('td', 'muted', c === 'total' ? '当前用量估算' : c === 'condition' ? '计费条件' : componentNames[c] + ' / 百万'));
        const vals = ms.map(m => c === 'total' ? cost(m) : amount(m, c));
        ms.forEach((m, i) => { const td = el('td', '', c === 'condition' ? m.options[m.variant].label : money(vals[i])); tr.append(td); });
        body.append(tr);
    } $('comparison-table').append(head, body); $('chart-unit').textContent = currency + (component === 'total' ? (en ? ' / selected usage' : ' / 当前用量') : (en ? ' / million tokens' : ' / 百万 tokens')); $('legend-input').textContent = component === 'total' ? '输入成本' : componentNames[component] + '单价'; $('legend-output').hidden = component !== 'total'; }
    function showDetails(m: WorkspaceModel) { $('detail-title').textContent = m.name; $('facts').replaceChildren(); for (const r of m.options[m.variant].rows) {
        const d = el('div', 'fact');
        d.append(el('h3', '', componentNames[r.component] || r.component), el('p', '', `${en ? 'Estimate' : '估算'}：${money(displayedAmount(r))} / ${en ? 'million tokens' : '百万 tokens'} · ${en ? 'Original quote' : '原始报价'}：${r.amount ?? '—'} ${r.currency} / ${r.unit_quantity} ${r.unit_name}`), el('p', '', condition(r)), el('p', '', `采集：${date(r.observed_at)} · ${r.field_state === 'confirmed' ? '已确认' : '旧数据 / 待核实'}`));
        if (r.stale_reason)
            d.append(el('p', '', r.stale_reason));
        const src = el('div');
        if (r.evidence_link) {
            const a = el('a', 'ev-link', '查看核价证据 ↗');
            a.href = r.evidence_link;
            src.append(a, el('span', 'small muted', '　摘录与定位 · 不可变'));
        }
        else if (r.source_url) {
            const a = el('a', 'ev-link', r.source_url + ' ↗');
            a.href = r.source_url;
            a.target = '_blank';
            a.rel = 'noopener';
            src.append(a);
        }
        else
            src.append(el('code', '', '暂无来源地址'));
        d.append(src);
        $('facts').append(d);
    } $('detail').showModal(); }
    $('compare-shortcut').onclick = () => $('compare').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('display-currency').onchange = () => { const value = $('display-currency').value; if(value !== 'USD' && value !== 'CNY')return; currency=value; currencyExplicit=true; updateFxLabel(); updateShareContext(); renderCatalog(); renderCompare(); renderHero(); };
    $('currency-shortcut').onclick = () => { $('fx-settings').scrollIntoView({ behavior: 'smooth', block: 'center' }); $('fx').focus({ preventScroll: true }); };
    $('close-detail').onclick = () => $('detail').close();
    $('search').oninput = e => { query = (e.currentTarget as HTMLInputElement | HTMLSelectElement).value.trim(); page = 0; renderProviders(); renderCatalog(); };
    $('model-filter').onchange = e => { modelIdFilter = (e.currentTarget as HTMLInputElement | HTMLSelectElement).value || null; familyIdFilter = null; filterError = null; page = 0; syncUrlState(); initSelectors(); renderProviders(); renderCatalog(); renderFilterSummary(); renderFilterError(); };
    $('family-filter').onchange = e => { familyIdFilter = (e.currentTarget as HTMLInputElement | HTMLSelectElement).value || null; modelIdFilter = null; filterError = null; page = 0; syncUrlState(); initSelectors(); renderProviders(); renderCatalog(); renderFilterSummary(); renderFilterError(); };
    $('sort').onchange = e => { sort = (e.currentTarget as HTMLInputElement | HTMLSelectElement).value; page = 0; renderCatalog(); };
    $('prev').onclick = () => { page--; renderCatalog(); };
    $('next').onclick = () => { page++; renderCatalog(); };
    $('clear').onclick = () => { selected.clear(); renderCatalog(); renderCompare(); renderHero(); };
    $('components').querySelectorAll('button').forEach(b => b.onclick = () => { component = b.dataset.component!; $('components').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b)); renderCompare(); });
    function volumes() { if(!$('input-volume').value||!$('output-volume').value||!$('input-volume').checkValidity()||!$('output-volume').checkValidity()){toast('请输入0至100万之间的用量（单位：百万 tokens）。');return false;} input = Number($('input-volume').value); output = Number($('output-volume').value); $('input-value').textContent = fmt(input); $('output-value').textContent = fmt(output); renderCompare(); return true; }
    function estimateCompleted() {
      if(Number.isFinite(input)&&Number.isFinite(output)&&input>=0&&output>=0&&input+output>0&&selectedModels().length>=1&&selectedModels().some(m=>{const n=cost(m);return n!==null&&Number.isFinite(n);}))recordWorkspaceResult('cost_estimate_completed_v2');
    }
    $('input-volume').onchange = () => {if(volumes())estimateCompleted();};
    $('output-volume').onchange = () => {if(volumes())estimateCompleted();};
    $('input-volume').oninput = volumes;
    $('output-volume').oninput = volumes;
    document.querySelectorAll<HTMLButtonElement>('[data-preset]').forEach(b => b.onclick = () => { const [i, o] = b.dataset.preset!.split(','); $('input-volume').value = i; $('output-volume').value = o; volumes(); estimateCompleted(); });
    $('fx').onchange = () => { const n = Number($('fx').value); if (!Number.isFinite(n) || n < .01 || n > 1000) {
        $('fx').value = String(fx);
        toast(en ? 'Enter an exchange rate between 0.01 and 1000.' : '请输入0.01至1000之间的汇率。');
        return;
    } fx = n; fxManual = true; updateFxLabel(); updateShareContext(); renderCatalog(); renderCompare(); renderHero(); };
    const syncTheme = () => { root.dataset.theme = document.documentElement.dataset.theme; };
    syncTheme();
    new MutationObserver(syncTheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    for (const [n, label] of [[providers.length, '家厂商'], [models.length, '个模型'], [rows.length, '条报价']])
        $('stats').append(append(el('div', 'stat'), el('strong', 'number', n), el('span', '', label)));
    $('updated').textContent = '更新于 ' + date(data.meta?.published_at);
    $('notice').append(el('span', '', data.meta?.partial ? '◌ 部分来源待更新' : '● 数据已收录'), el('span', '', data.meta?.partial ? (data.meta.failed_sources || []).map(p => name(String(p).split(':')[0])).join('、') + ' 本次未完整抓取，相关记录可能保留旧报价。可在模型详情中查看。' : '报价来自当前已发布数据，实际计费请以厂商说明为准。'));
    $('footer-meta').textContent = `数据版本 ${data.meta?.artifact_version ?? '—'} · ${date(data.meta?.published_at)} · 金额按当前汇率估算`;
    parseUrlFilter();
    const queryUsage=new URLSearchParams(location.search);const hasUsage=queryUsage.has('input')||queryUsage.has('output');
    for(const key of ['input','output'])if(queryUsage.has(key)){const raw=queryUsage.get(key)!,n=Number(raw);if(raw.trim()&&Number.isFinite(n)&&n>=0&&n<=1000000){if(key==='input')input=n;else output=n;}else toast('用量参数无效，请手动输入。');}
    let shared:ReturnType<typeof readCalculation>=null,entryError='';
    try{shared=readCalculation(location.hash);}catch(e){entryError=(e as Error).message;selected.clear();}
    if(modelIdFilter){selected.clear();const match=models.find(m=>m.modelId===modelIdFilter);if(match)selected.add(match.key);else entryError='该模型暂没有可计算的报价，请选择其他模型。';}
    if(shared){selected.clear();modelIdFilter=null;familyIdFilter=null;input=shared.input;output=shared.output;fx=shared.fx;fxManual=true;currency=shared.v===1?'CNY':shared.currency;currencyExplicit=true;
      for(const key of shared.selected){const m=map.get(key),variant=shared.variants.find(v=>v[0]===key)?.[1],index=m?.options.findIndex(v=>v.key===variant)??-1;
        if(!m||index<0){entryError='分享中的部分模型或计费条件已不可用，未自动替换。请重新选择后计算。';continue;}m.variant=index;selected.add(key);}
    }
    const status=document.getElementById('share-status')!;
    function updateShareContext(){if(shared&&!entryError)status.textContent=en?`Shared observation: ${shared.asOf}. Recalculated in ${currency} with current quotes; 1 USD = ${fx} CNY (estimate).`:`分享时的数据时间：${shared.asOf}。当前按本页最新报价以 ${currency} 重算，汇率假设 1 USD = ${fx} CNY。`;}
    updateShareContext();
    if(entryError)status.textContent=entryError;
    $('input-volume').value=String(input);$('output-volume').value=String(output);updateFxLabel();
    initSelectors();
    renderFilterSummary();
    renderFilterError();
    renderProviders();
    renderCatalog();
    renderCompare();
    renderHero();
    type SavedWorkspace = { provider: string; query: string; sort: string; modelId: string | null; familyId: string | null; selected: string[]; variants: [string, string][]; component: string; input: number; output: number; fx: number | null; currency?: 'USD' | 'CNY' };
    const initialFilter = { modelId: modelIdFilter, familyId: familyIdFilter, error: filterError };
    const defaultSelection = [...selected]; const defaultFx = fx;
    const snapshot = (): SavedWorkspace => ({ provider, query, sort, modelId: modelIdFilter, familyId: familyIdFilter, selected: [...selected], variants: models.filter(m => selected.has(m.key)).map(m => [m.key, m.options[m.variant].key]), component, input, output, currency, fx: fxManual ? fx : null });
    const defaults: SavedWorkspace = { provider: providers[0] || '', query: '', sort: 'name', modelId: null, familyId: null, selected: defaultSelection, variants: [], component: 'total', input: 1, output: .25, currency: defaultCurrency, fx: null };
    let forced:SavedWorkspace|null=(shared||modelIdFilter||entryError||hasUsage)?snapshot():null;
    const save = savedState<SavedWorkspace>('priceWorkspace', defaults, value => {
      if(forced)value={...forced,currency:currencyExplicit?forced.currency:value.currency??forced.currency};
      provider = providers.includes(value.provider) ? value.provider : providers[0] || ''; query = value.query; sort = value.sort;
      modelIdFilter = catalogModels.some(m => m.modelId === value.modelId) ? value.modelId : null;
      familyIdFilter = modelIdFilter ? null : catalogFamilies.some(f => f.familyId === value.familyId) ? value.familyId : null;
      filterError = null;
      if (initialFilter.modelId || initialFilter.familyId || initialFilter.error) { modelIdFilter = initialFilter.modelId; familyIdFilter = initialFilter.familyId; filterError = initialFilter.error; }
      selected.clear(); value.selected.filter(key => models.some(m => m.key === key)).slice(0,5).forEach(key => selected.add(key));
      models.forEach(m => { const variant = value.variants.find(v => v[0] === m.key)?.[1]; const index = m.options.findIndex(v => v.key === variant); m.variant = index < 0 ? 0 : index; });
      currency = value.currency === 'USD' || value.currency === 'CNY' ? value.currency : defaultCurrency;
      component = value.component; input = value.input; output = value.output; fx = value.fx ?? defaultFx; fxManual = value.fx !== null;
      $('search').value = query; $('sort').value = sort; $('input-volume').value = String(input); $('output-volume').value = String(output); $('input-value').textContent = fmt(input); $('output-value').textContent = fmt(output); $('fx').value = String(fx); page = 0;
      $('components').querySelectorAll<HTMLButtonElement>('button').forEach(button => button.classList.toggle('active', button.dataset.component === component));
      updateFxLabel(); initSelectors(); renderProviders(); renderCatalog(); renderCompare(); renderHero(); renderFilterSummary(); renderFilterError();
    });
    const persist = () => {if(!$('input-volume').checkValidity()||!$('output-volume').checkValidity()||!$('input-volume').value||!$('output-volume').value)return;if(forced)forced=snapshot();save(snapshot());};
    const requireResult=()=>{if(!volumes()||input+output<=0||!selectedModels().length||selectedModels().every(m=>cost(m)===null))throw Error('请先选择有完整报价的模型，输入有效用量并完成计算。');};
    const summary=()=>[
      'MaaS Daily · '+(en?'Usage cost estimate':'当前用量成本估算'),
      en?`Input ${input} million / output ${output} million tokens; currency ${currency}; 1 USD = ${fx} CNY (estimate).`:`输入 ${input} 百万 / 输出 ${output} 百万 tokens；币种 ${currency}；估算汇率 1 USD = ${fx} CNY。`,
      ...selectedModels().map(m=>`${m.name}: ${money(cost(m))}; ${en?JSON.stringify(m.options[m.variant].rows.map(r=>({region:r.region,billing:r.billing_mode,tier:r.service_tier,context:r.context_band,time:r.time_condition}))):m.options[m.variant].label}`),
      (en?'Observed ':'报价时间 ')+date(data.meta.published_at),
      en?'Excludes cache discounts, taxes and extra fees. Links recalculate with current quotes.':'未计缓存优惠、税费及附加项。分享打开后按当前报价重算。'
    ].join('\n');
    const copy=async(kind:'calculation_link'|'calculation_summary')=>{try{requireResult();const value=kind==='calculation_link'?calculationLink(location.href,{v:2,currency,selected:[...selected],variants:snapshot().variants,input,output,fx,asOf:date(data.meta.published_at)}):summary();await navigator.clipboard.writeText(value);document.dispatchEvent(new CustomEvent('maas:copy-success',{detail:{kind}}));status.textContent=kind==='calculation_link'?'结果链接已复制，链接包含用量假设，对方将按当前报价重算。':'费用摘要已复制。';}catch(e){status.textContent=(e as Error).message||'复制失败，请检查浏览器剪贴板权限。';}};
    document.getElementById('share-result')!.onclick=()=>void copy('calculation_link');document.getElementById('copy-result')!.onclick=()=>void copy('calculation_summary');
    let pendingSave=false,pendingFollow=false;
    const followSelected=async()=>{const ids=[...new Set(selectedModels().map(m=>m.modelId).filter((x):x is string=>Boolean(x)))];if(!ids.length){status.textContent=en?'No model identities available to follow.':'所选报价没有可关注的模型标识，请打开模型详情核对。';return;}
      const results=await Promise.allSettled(ids.map(modelId=>accountApi('watch',{modelId})));const done=results.filter(r=>r.status==='fulfilled').length;status.textContent=en?`Followed ${done}/${ids.length} models. Manage email reminders in your account.`:`已关注 ${done}/${ids.length} 个模型。邮件提醒可在账户中心单独开启。`;try{await refreshAccount();}catch{}}
    document.getElementById('follow-selected')!.onclick=()=>{forced=snapshot();if(!currentAccount()){pendingFollow=true;openAccountLogin();return;}void followSelected();};
    const finishSave=async()=>{try{save(snapshot());await flushAccountState();status.textContent='计算已保存，可在此页面继续使用。';}catch{status.textContent='保存失败，请稍后重试。';}};
    document.getElementById('save-result')!.onclick=()=>{try{requireResult();forced=snapshot();if(!currentAccount()){pendingSave=true;openAccountLogin();status.textContent='登录后保存这组计算。';return;}void finishSave();}catch(e){status.textContent=(e as Error).message;}};
    onAccountChange(user=>{if(user&&pendingSave){pendingSave=false;void finishSave();}if(user&&pendingFollow){pendingFollow=false;void followSelected();}});
    root.addEventListener('input', persist); root.addEventListener('change', persist);
    root.addEventListener('click', event => { if ((event.target as HTMLElement).closest('button') && !(event.target as HTMLElement).closest('#theme')) persist(); });
    $('search').maxLength = 200;
    window.addEventListener('popstate', () => { parseUrlFilter(); initSelectors(); renderProviders(); renderCatalog(); renderFilterSummary(); renderFilterError(); persist(); });
}
startPriceWorkspace();
