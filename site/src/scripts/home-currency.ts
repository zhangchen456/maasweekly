const toolbar = document.querySelector<HTMLElement>('[data-home-fx]');
if (toolbar) {
  let rate = Number(toolbar.dataset.homeFx);
  let currency = 'CNY';
  const input = document.getElementById('home-fx-rate') as HTMLInputElement;
  const status = document.getElementById('home-fx-status')!;
  const format = new Intl.NumberFormat('zh-CN', { maximumSignificantDigits: 6 });
  function render() {
    document.querySelectorAll<HTMLElement>('[data-quote-amount]').forEach(quote => {
      const original = quote.dataset.quoteCurrency;
      const amount = Number(quote.dataset.quoteAmount);
      if (!['CNY', 'USD'].includes(original ?? '') || !Number.isFinite(amount)) return;
      const converted = original === currency ? amount : currency === 'CNY' ? amount * rate : amount / rate;
      quote.textContent = format.format(converted);
      quote.closest('td')!.querySelector('[data-display-currency]')!.textContent = currency;
    });
    toolbar!.querySelectorAll<HTMLButtonElement>('[data-currency]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.currency === currency)));
  }
  toolbar.querySelectorAll<HTMLButtonElement>('[data-currency]').forEach(button => button.addEventListener('click', () => {
    currency = button.dataset.currency!;
    render();
  }));
  input.addEventListener('change', () => {
    const next = Number(input.value);
    if (!Number.isFinite(next) || next < .01 || next > 1000) {
      input.value = String(rate);
      status.textContent = '请输入 0.01–1000 之间的汇率';
      return;
    }
    rate = next;
    status.textContent = '';
    document.getElementById('home-fx-note')!.textContent = '自定义汇率 · 非实时';
    render();
  });
}
