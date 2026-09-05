for (const switches of document.querySelectorAll<HTMLElement>('.board-switches')) {
  const buttons = [...switches.querySelectorAll<HTMLButtonElement>('[data-board]')];
  const available = buttons.filter(b => document.getElementById(b.dataset.board!));
  buttons.filter(b => !available.includes(b)).forEach(b => b.hidden = true);
  function activate(button: HTMLButtonElement) {
    available.forEach(b => {
      const active = b === button;
      b.setAttribute('aria-pressed', String(active));
      document.getElementById(b.dataset.board!)!.hidden = !active;
    });
  }
  if (available[0]) activate(available[0]);
  available.forEach((button,index) => {
    button.addEventListener('click', () => activate(button));
    button.addEventListener('keydown', event => {
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const target = event.key === 'Home' ? 0 : event.key === 'End' ? available.length-1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + available.length) % available.length;
      available[target].focus(); activate(available[target]);
    });
  });
}
for (const widget of document.querySelectorAll<HTMLElement>('.rank-widget')) {
  const body = widget.querySelector('tbody')!;
  const rows = [...body.querySelectorAll<HTMLTableRowElement>('tr')];
  const input = widget.querySelector<HTMLInputElement>('input[type="search"]')!;
  const selected = new Set<HTMLTableRowElement>();
  const status = widget.querySelector('.compare-status')!;
  function filter() {
    const query = input.value.trim().toLowerCase();
    rows.forEach(row => row.hidden = !row.textContent?.toLowerCase().includes(query));
    const count = rows.filter(row => !row.hidden).length;
    widget.querySelector('.table-count')!.textContent = `${count} / ${rows.length} 条记录`;
    (widget.querySelector('.table-empty') as HTMLElement).hidden = count > 0;
  }
  input.addEventListener('input', filter);
  widget.querySelector('.reset-search')?.addEventListener('click', () => { input.value = ''; filter(); input.focus(); });
  widget.querySelectorAll<HTMLButtonElement>('[data-sort]').forEach(button => button.addEventListener('click', () => {
    const th = button.closest('th')!;
    const ascending = th.getAttribute('aria-sort') !== 'ascending';
    widget.querySelectorAll('th[aria-sort]').forEach(el => { el.setAttribute('aria-sort','none'); el.querySelector('button span')!.textContent = '↕'; });
    th.setAttribute('aria-sort',ascending ? 'ascending' : 'descending');
    button.querySelector('span')!.textContent = ascending ? '↑' : '↓';
    const key = button.dataset.sort!;
    const value = (row: HTMLTableRowElement) => row.querySelector<HTMLElement>(`.c-${key}`)?.dataset.value || '';
    [...rows].sort((a,b) => {
      const av = value(a), bv = value(b);
      if (!av || !bv) return av ? -1 : bv ? 1 : Number(a.dataset.order)-Number(b.dataset.order);
      const difference = Number.isFinite(Number(av)) && Number.isFinite(Number(bv)) ? Number(av)-Number(bv) : av.localeCompare(bv,'zh-CN',{numeric:true});
      return (ascending ? difference : -difference) || Number(a.dataset.order)-Number(b.dataset.order);
    }).forEach(row=>body.append(row));
  }));
  function renderComparison() {
    const container = widget.querySelector('.comparison-items')!;
    container.replaceChildren();
    selected.forEach(row => {
      const card = document.createElement('article');
      const title = document.createElement('span'); title.textContent = row.dataset.name || '';
      const value = document.createElement('strong'); value.textContent = row.dataset.metric || '—';
      const label = document.createElement('small'); label.textContent = `${widget.dataset.metric || ''}${row.querySelector('.c-harness') ? ' · ' + row.querySelector('.c-harness')!.textContent + ' · ' + row.querySelector('.c-turn_range')!.textContent : ''}`;
      card.append(title,value,label); container.append(card);
    });
    (widget.querySelector('.comparison') as HTMLElement).hidden = !selected.size;
    rows.forEach(row => { row.classList.toggle('is-selected',selected.has(row)); row.querySelector<HTMLInputElement>('.compare-check')!.checked = selected.has(row); });
  }
  rows.forEach(row => row.querySelector<HTMLInputElement>('.compare-check')!.addEventListener('change',event => {
    const checkbox = event.target as HTMLInputElement;
    if (checkbox.checked && selected.size >= 3) { checkbox.checked = false; status.textContent = '最多比较 3 项，请先取消一项。'; return; }
    checkbox.checked ? selected.add(row) : selected.delete(row);
    status.textContent = selected.size ? `已选择 ${selected.size} 项；搜索和排序不会清除已选项。` : '';
    renderComparison();
  }));
  widget.querySelector('.clear-compare')?.addEventListener('click', () => { selected.clear(); status.textContent = ''; renderComparison(); });
}
