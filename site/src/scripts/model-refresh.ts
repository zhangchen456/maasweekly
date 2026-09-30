import { priceCells, priceHeaders } from '../lib/price-display';
import type { PriceRecord, ChangeRecord } from '../lib/release';

const root = document.querySelector<HTMLElement>('.model-detail');
const button = document.getElementById('refresh-model') as HTMLButtonElement | null;
const status = document.getElementById('refresh-status');
if (root && button && status) {
  const { apiBase, modelId, datasetVersion, from, to } = root.dataset;
  async function fetchPage(url: string) {
    const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error('暂时无法获取数据');
    const data = await response.json();
    if (data.datasetVersion !== datasetVersion) throw new Error('数据版本已更新，请重新打开本页');
    return data;
  }
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = '正在核对当前数据…';
    try {
      // Follow fixed-version cursors before replacing the complete static table.
      const prices: PriceRecord[] = [];
      let url: string | null = `${apiBase}/prices?modelId=${encodeURIComponent(modelId!)}&limit=100`;
      const seen = new Set<string>();
      while (url) {
        if (seen.has(url)) throw new Error('分页响应异常');
        seen.add(url);
        const data = await fetchPage(url);
        prices.push(...data.items);
        url = data.page.nextCursor ? `${apiBase}/prices?cursor=${encodeURIComponent(data.page.nextCursor)}` : null;
      }
      const data = await fetchPage(`${apiBase}/changes?modelId=${encodeURIComponent(modelId!)}&from=${from}&to=${to}&limit=10`);
      const changes: ChangeRecord[] = data.items;
      const table = document.createElement('table'); table.className = 'price-table';
      const head = table.createTHead().insertRow();
      for (const label of [...priceHeaders, '证据 / 变化']) {
        const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; head.append(th);
      }
      const body = table.createTBody();
      for (const price of prices) {
        const row = body.insertRow(); row.dataset.priceId = price.id;
        for (const value of priceCells(price)) row.insertCell().textContent = value;
        const cell = row.insertCell();
        if (price.evidenceId) {
          const a = document.createElement('a'); a.href = `/evidence/${price.evidenceId}/`; a.textContent = '价格证据'; cell.append(a);
        }
        if (price.links.itemPermalink) {
          const a = document.createElement('a'); a.href = price.links.itemPermalink; a.textContent = '变化记录'; cell.append(' · ', a);
        }
        if (!cell.textContent) cell.textContent = '暂无链接';
      }
      const cards = document.createDocumentFragment();
      for (const change of changes) {
        const card = document.createElement('article'); card.className = 'change-card';
        const head = document.createElement('div'); head.className = 'change-head';
        const date = document.createElement('time'); date.dateTime = change.observationDate; date.textContent = change.observationDate;
        const type = document.createElement('span'); type.className = 'change-type'; type.textContent = change.recordType === 'price_change' ? '价格事件' : '来源观察';
        const a = document.createElement('a'); a.className = 'change-title'; a.href = change.links.permalink; a.textContent = change.title;
        head.append(date, type); card.append(head, a);
        if (change.summary) { const p = document.createElement('p'); p.className = 'change-summary'; p.textContent = change.summary.slice(0, 160); card.append(p); }
        cards.append(card);
      }
      document.getElementById('current-prices')!.replaceChildren(prices.length ? table : '当前公开数据范围内暂无价格记录。');
      document.getElementById('recent-changes')!.replaceChildren(changes.length ? cards : '当前数据窗口内暂无变化记录。');
      const keys = document.createDocumentFragment();
      for (const key of [...new Set(prices.map(p => p.modelKey))].sort()) {
        const tag = document.createElement('span'); tag.className = 'model-key-tag'; tag.textContent = key; keys.append(tag);
      }
      document.getElementById('model-keys')!.replaceChildren(prices.length ? keys : '当前数据中暂无可观察的 API 模型名。');
      status.textContent = '已核对当前版本的数据。';
    } catch (error) {
      status.textContent = `${error instanceof Error ? error.message : '刷新失败'}；页面已有数据已保留。`;
    } finally { button.disabled = false; }
  });
}
