import { formatTimestamp } from '../../public/time-display.js';
import { savedState } from './account-client';
import type { WorkspaceData, LedgerPrice, WorkspaceModel, PriceVariant, SourceCondition } from '../lib/pricing-workspace';
interface WorkspaceElements {
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
    const rate = Number(snap.rates?.USD);
    if (snap.base === 'CNY' && rate > 0 && Number.isFinite(rate)) {
        fx = rate;
        fxManual = false;
    }
    $('fx').value = String(fx);
    function updateFxLabel() { $('currency-shortcut').textContent = '¥ 人民币 · 汇率 ' + fmt(fx); $('fx-label').textContent = fxManual ? '手动估算 · 非实时汇率' : '系统汇率 · ' + date(snap.effective_at); }
    updateFxLabel();
    function cny(r: LedgerPrice | undefined) { if (!r || !['token', 'tokens'].includes(r.unit_name))
        return null; const n = num(r.amount_per_1m); if (n === null)
        return null; if (r.currency === 'CNY')
        return n; if (r.currency === 'USD')
        return n * fx; const converted = num(r.converted_amount_per_1m); return r.converted_currency === 'CNY' ? converted : null; }
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
    function amount(m: WorkspaceModel, c: string): number | null { const rs = facts(m, c); const values = rs.map(cny).filter(n => n !== null); if (!values.length)
        return null; const distinct = [...new Set(values)]; return distinct.length === 1 ? distinct[0] : Math.min(...distinct); }
    function priceRange(m: WorkspaceModel, c: string) { const rs = facts(m, c); const values = rs.map(cny).filter(n => n !== null); const distinct = [...new Set(values)]; return distinct.length > 1 ? [Math.min(...distinct), Math.max(...distinct)] : null; }
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
        selected.add(m.key); renderCatalog(); renderCompare(); renderHero(); }
    function renderProviders() { $('providers').replaceChildren(); for (const p of providers) {
        const count = models.filter(m => m.provider === p).length;
        const b = el('button', 'provider' + (p === provider && !query ? ' active' : ''));
        b.setAttribute('aria-pressed', String(p === provider && !query));
        append(b, providerMark(p), append(el('div'), el('b', '', name(p)), el('small', '', brands[p]?.[1] || p)), el('span', 'count', count));
        b.onclick = () => { provider = p; query = ''; $('search').value = ''; page = 0; renderProviders(); renderCatalog(); };
        $('providers').append(b);
    } }
    function cellPrice(m: WorkspaceModel, c: string) { const td = el('td'), v = amount(m, c), rg = priceRange(m, c); const price = el('span', 'price'); if (v !== null)
        price.append(el('em', '', '¥')); price.append(document.createTextNode(fmt(v))); if (rg)
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
        append(row, label, append(el('div', 'mini-track'), fill), el('b', 'number', n === null ? '暂无' : '¥' + fmt(n)));
        $('hero-chart').append(row);
    } }
    function renderCompare() { const ms = selectedModels(); $('compare-shortcut').textContent = '对比 ' + ms.length + ' / 5 ↓'; $('selection').replaceChildren(); for (const m of ms) {
        const b = append(el('button', '', m.name), el('span', '', '×'));
        b.setAttribute('aria-label', '从对比移除 ' + m.name);
        b.onclick = () => toggle(m);
        $('selection').append(b);
    } $('plot').replaceChildren(); $('comparison-table').replaceChildren(); $('comparison-note').textContent = ms.some(stale) ? '含旧数据，请结合模型详情中的采集日期与来源核对。' : '各模型采用上方选定的计费条件；不同区域、上下文和时段可能影响价格。'; if (ms.length < 2) {
        $('plot').append(el('div', 'empty', ms.length ? '再加入 1 个模型，即可开始对比。' : '在模型目录中加入 2–5 个模型，开始比较。'));
        return;
    } const max = Math.max(...ms.map(m => metric(m) || 0), .01); for (const m of ms) {
        const n = metric(m);
        const row = el('div', 'plot-row'), label = append(el('div', 'plot-label', m.name), el('small', '', name(m.provider) + (stale(m) ? ' · 旧数据' : '')));
        const track = el('div', 'track');
        track.setAttribute('aria-label', m.name + ' ' + (n === null ? '暂无可比报价' : fmt(n) + ' 元'));
        if (n !== null) {
            const a = el('div', 'bar input-bar'), b = el('div', 'bar output-bar');
            a.style.width = ((component === 'total' ? (amount(m, 'input') || 0) * input : n) / max * 100) + '%';
            b.style.width = (component === 'total' ? (amount(m, 'output') || 0) * output / max * 100 : 0) + '%';
            track.append(a, b);
        }
        row.append(label, track, el('div', 'plot-price number', n === null ? '暂无' : '¥' + fmt(n)));
        $('plot').append(row);
    } const head = el('thead'), hr = append(el('tr'), el('th', '', '价格 / 条件')); ms.forEach(m => hr.append(el('th', '', m.name))); head.append(hr); const body = el('tbody'); for (const c of ['input', 'output', 'cache_read', 'cache_write', 'total', 'condition']) {
        const tr = append(el('tr'), el('td', 'muted', c === 'total' ? '当前用量估算' : c === 'condition' ? '计费条件' : componentNames[c] + ' / 百万'));
        const vals = ms.map(m => c === 'total' ? cost(m) : amount(m, c)), minimum = Math.min(...vals.filter(v => v !== null));
        ms.forEach((m, i) => { const td = el('td', c !== 'condition' && vals[i] !== null && vals[i] === minimum ? 'winner' : '', c === 'condition' ? m.options[m.variant].label : vals[i] === null ? '暂无' : '¥' + fmt(vals[i])); tr.append(td); });
        body.append(tr);
    } $('comparison-table').append(head, body); $('chart-unit').textContent = component === 'total' ? '元 / 当前用量' : '元 / 百万 tokens'; $('legend-input').textContent = component === 'total' ? '输入成本' : componentNames[component] + '单价'; $('legend-output').hidden = component !== 'total'; }
    function showDetails(m: WorkspaceModel) { $('detail-title').textContent = m.name; $('facts').replaceChildren(); for (const r of m.options[m.variant].rows) {
        const d = el('div', 'fact');
        d.append(el('h3', '', componentNames[r.component] || r.component), el('p', '', `人民币：${cny(r) === null ? '暂无' : '¥' + fmt(cny(r)) + ' / 百万 tokens'} · 原始报价：${r.amount ?? '暂无'} ${r.currency} / ${r.unit_quantity} ${r.unit_name}`), el('p', '', condition(r)), el('p', '', `采集：${date(r.observed_at)} · ${r.field_state === 'confirmed' ? '已确认' : '旧数据 / 待核实'}`));
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
    function volumes() { input = Number($('input-volume').value); output = Number($('output-volume').value); $('input-value').textContent = fmt(input); $('output-value').textContent = fmt(output); renderCompare(); }
    $('input-volume').oninput = volumes;
    $('output-volume').oninput = volumes;
    document.querySelectorAll<HTMLButtonElement>('[data-preset]').forEach(b => b.onclick = () => { const [i, o] = b.dataset.preset!.split(','); $('input-volume').value = i; $('output-volume').value = o; volumes(); });
    $('fx').onchange = () => { const n = Number($('fx').value); if (!Number.isFinite(n) || n <= 0 || n > 1000) {
        $('fx').value = String(fx);
        toast('请输入大于 0、且不超过 1000 的汇率。');
        return;
    } fx = n; fxManual = true; updateFxLabel(); renderCatalog(); renderCompare(); renderHero(); };
    window.addEventListener('message', event => { if (event.source !== parent || event.data?.type !== 'zhuilang:appearance' || !['light', 'dark'].includes(event.data.theme))
        return; root.dataset.theme = event.data.theme; $('theme').setAttribute('aria-label', event.data.theme === 'light' ? '切换深色外观' : '切换浅色外观'); userToggledTheme = false; });
    let userToggledTheme = false;
    (function initTheme() { const mq = matchMedia('(prefers-color-scheme: dark)'); const apply = (dark: boolean) => { if (userToggledTheme)
        return; root.dataset.theme = dark ? 'dark' : 'light'; $('theme').setAttribute('aria-label', dark ? '切换浅色外观' : '切换深色外观'); }; apply(mq.matches); mq.addEventListener('change', e => apply(e.matches)); })();
    $('theme').onclick = () => { const light = root.dataset.theme !== 'light'; root.dataset.theme = light ? 'light' : 'dark'; $('theme').setAttribute('aria-label', light ? '切换深色外观' : '切换浅色外观'); userToggledTheme = true; };
    for (const [n, label] of [[providers.length, '家厂商'], [models.length, '个模型'], [rows.length, '条报价']])
        $('stats').append(append(el('div', 'stat'), el('strong', 'number', n), el('span', '', label)));
    $('updated').textContent = '更新于 ' + date(data.meta?.published_at);
    $('notice').append(el('span', '', data.meta?.partial ? '◌ 部分来源待更新' : '● 数据已收录'), el('span', '', data.meta?.partial ? (data.meta.failed_sources || []).map(p => name(String(p).split(':')[0])).join('、') + ' 本次未完整抓取，相关记录可能保留旧报价。可在模型详情中查看。' : '报价来自当前已发布数据，实际计费请以厂商说明为准。'));
    $('footer-meta').textContent = `数据版本 ${data.meta?.artifact_version ?? '—'} · ${date(data.meta?.published_at)} · 金额按当前汇率估算`;
    parseUrlFilter();
    initSelectors();
    renderFilterSummary();
    renderFilterError();
    renderProviders();
    renderCatalog();
    renderCompare();
    renderHero();
    type SavedWorkspace = { provider: string; query: string; sort: string; modelId: string | null; familyId: string | null; selected: string[]; variants: [string, string][]; component: string; input: number; output: number; fx: number | null };
    const initialFilter = { modelId: modelIdFilter, familyId: familyIdFilter, error: filterError };
    const defaultSelection = [...selected]; const defaultFx = fx;
    const snapshot = (): SavedWorkspace => ({ provider, query, sort, modelId: modelIdFilter, familyId: familyIdFilter, selected: [...selected], variants: models.filter(m => selected.has(m.key)).map(m => [m.key, m.options[m.variant].key]), component, input, output, fx: fxManual ? fx : null });
    const defaults: SavedWorkspace = { provider: providers[0] || '', query: '', sort: 'name', modelId: null, familyId: null, selected: defaultSelection, variants: [], component: 'total', input: 1, output: .25, fx: null };
    const save = savedState<SavedWorkspace>('priceWorkspace', defaults, value => {
      provider = providers.includes(value.provider) ? value.provider : providers[0] || ''; query = value.query; sort = value.sort;
      modelIdFilter = catalogModels.some(m => m.modelId === value.modelId) ? value.modelId : null;
      familyIdFilter = modelIdFilter ? null : catalogFamilies.some(f => f.familyId === value.familyId) ? value.familyId : null;
      filterError = null;
      if (initialFilter.modelId || initialFilter.familyId || initialFilter.error) { modelIdFilter = initialFilter.modelId; familyIdFilter = initialFilter.familyId; filterError = initialFilter.error; }
      selected.clear(); value.selected.filter(key => models.some(m => m.key === key)).slice(0,5).forEach(key => selected.add(key));
      models.forEach(m => { const variant = value.variants.find(v => v[0] === m.key)?.[1]; const index = m.options.findIndex(v => v.key === variant); m.variant = index < 0 ? 0 : index; });
      component = value.component; input = value.input; output = value.output; fx = value.fx ?? defaultFx; fxManual = value.fx !== null;
      $('search').value = query; $('sort').value = sort; $('input-volume').value = String(input); $('output-volume').value = String(output); $('input-value').textContent = fmt(input); $('output-value').textContent = fmt(output); $('fx').value = String(fx); page = 0;
      $('components').querySelectorAll<HTMLButtonElement>('button').forEach(button => button.classList.toggle('active', button.dataset.component === component));
      updateFxLabel(); initSelectors(); renderProviders(); renderCatalog(); renderCompare(); renderHero(); renderFilterSummary(); renderFilterError();
    });
    const persist = () => save(snapshot());
    root.addEventListener('input', persist); root.addEventListener('change', persist);
    root.addEventListener('click', event => { if ((event.target as HTMLElement).closest('button') && !(event.target as HTMLElement).closest('#theme')) persist(); });
    $('search').maxLength = 200;
    document.addEventListener('maas:appearance-restored', event => { root.dataset.theme = (event as CustomEvent<string>).detail; userToggledTheme = true; });
    $('theme').addEventListener('click', () => document.dispatchEvent(new CustomEvent('maas:theme-change', { detail: root.dataset.theme })));
    window.addEventListener('popstate', () => { parseUrlFilter(); initSelectors(); renderProviders(); renderCatalog(); renderFilterSummary(); renderFilterError(); persist(); });
}
startPriceWorkspace();
