import { priceCells, priceHeaders, englishPriceCells, englishPriceHeaders } from '../lib/price-display';
import type { PriceRecord, ChangeRecord } from '../lib/release';

const root = document.querySelector<HTMLElement>('.model-detail');
const button = document.getElementById('refresh-model') as HTMLButtonElement | null;
const status = document.getElementById('refresh-status');
if (root && button && status) {
  const en = root.dataset.locale === 'en';
  const t = (zh: string, english: string) => en ? english : zh;
  const cells = en ? englishPriceCells : priceCells;
  const headers = en ? englishPriceHeaders : priceHeaders;
  const { apiBase, modelId, datasetVersion, from, to } = root.dataset;
  async function fetchPage(url: string) {
    const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error(t('暂时无法获取数据', 'Data is temporarily unavailable'));
    const data = await response.json();
    if (data.datasetVersion !== datasetVersion) throw new Error(t('数据版本已更新，请重新打开本页', 'The dataset version has changed. Please reopen this page'));
    return data;
  }
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = t('正在核对当前数据…', 'Checking current data…');
    try {
      // Follow fixed-version cursors before replacing the complete static table.
      const prices: PriceRecord[] = [];
      let url: string | null = `${apiBase}/prices?modelId=${encodeURIComponent(modelId!)}&limit=100`;
      const seen = new Set<string>();
      while (url) {
        if (seen.has(url)) throw new Error(t('分页响应异常', 'Unexpected pagination response'));
        seen.add(url);
        const data = await fetchPage(url);
        prices.push(...data.items);
        url = data.page.nextCursor ? `${apiBase}/prices?cursor=${encodeURIComponent(data.page.nextCursor)}` : null;
      }
      const data = await fetchPage(`${apiBase}/changes?modelId=${encodeURIComponent(modelId!)}&from=${from}&to=${to}&limit=10`);
      const changes: ChangeRecord[] = data.items;
      const table = document.createElement('table'); table.className = 'price-table';
      const head = table.createTHead().insertRow();
      for (const label of [...headers, t('证据 / 变化', 'Evidence / record')]) {
        const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; head.append(th);
      }
      const body = table.createTBody();
      for (const price of prices) {
        const row = body.insertRow(); row.dataset.priceId = price.id;
        for (const value of cells(price)) row.insertCell().textContent = value;
        const cell = row.insertCell();
        if (price.evidenceId) {
          const a = document.createElement('a'); a.href = `/evidence/${price.evidenceId}/`; a.textContent = t('价格证据', 'Evidence (Chinese)'); cell.append(a);
        }
        if (price.links.itemPermalink) {
          const a = document.createElement('a'); a.href = price.links.itemPermalink; a.textContent = t('变化记录', 'Record (Chinese)'); cell.append(' · ', a);
        }
        if (!cell.textContent) cell.textContent = t('暂无链接', 'No link available');
      }
      const cards = document.createDocumentFragment();
      for (const change of changes) {
        const card = document.createElement('article'); card.className = 'change-card';
        const head = document.createElement('div'); head.className = 'change-head';
        const date = document.createElement('time'); date.dateTime = change.observationDate; date.textContent = change.observationDate;
        const type = document.createElement('span'); type.className = 'change-type'; type.textContent = change.recordType === 'price_change' ? t('价格事件', 'Pricing observation') : t('来源观察', 'Source observation');
        const a = document.createElement('a'); a.className = 'change-title'; a.href = change.links.permalink; a.textContent = en ? `${change.recordType === 'price_change' ? 'Pricing observation' : 'Source observation'} (Chinese)` : change.title;
        head.append(date, type); card.append(head, a);
        if (change.summary && !en) { const p = document.createElement('p'); p.className = 'change-summary'; p.textContent = change.summary.slice(0, 160); card.append(p); }
        cards.append(card);
      }
      document.getElementById('current-prices')!.replaceChildren(prices.length ? table : t('当前公开数据范围内暂无价格记录。', 'No pricing records in the current public dataset. This does not imply free or unavailable service.'));
      document.getElementById('recent-changes')!.replaceChildren(changes.length ? cards : t('当前数据窗口内暂无变化记录。', 'No observations in the current data window.'));
      const keys = document.createDocumentFragment();
      for (const key of [...new Set(prices.map(p => p.modelKey))].sort()) {
        const tag = document.createElement('span'); tag.className = 'model-key-tag'; tag.textContent = key; keys.append(tag);
      }
      document.getElementById('model-keys')!.replaceChildren(prices.length ? keys : t('当前数据中暂无可观察的 API 模型名。', 'No observed API model names in the current dataset.'));
      status.textContent = t('已核对当前版本的数据。', 'Current dataset records checked.');
    } catch (error) {
      status.textContent = `${error instanceof Error ? error.message : t('刷新失败', 'Refresh failed')}${t('；页面已有数据已保留。', '; the existing page data has been retained.')}`;
    } finally { button.disabled = false; }
  });
}
