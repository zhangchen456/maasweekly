document.querySelectorAll<HTMLElement>('[data-model-tabs]').forEach(root => {
  const tabs = Array.from(root.querySelectorAll<HTMLButtonElement>('[data-model-tab]'));
  const panel = root.querySelector<HTMLElement>('[role="tabpanel"]');
  const activate = (tab: HTMLButtonElement, focus = false) => {
    tabs.forEach(item => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
    });
    root.querySelectorAll<HTMLElement>('[data-home-group], [data-model-description]').forEach(item => {
      item.hidden = (item.dataset.homeGroup ?? item.dataset.modelDescription) !== tab.dataset.modelTab;
    });
    panel?.setAttribute('aria-labelledby', tab.id);
    if (focus) tab.focus();
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activate(tab));
    tab.addEventListener('keydown', event => {
      const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length
        : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
        : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null;
      if (next === null) return;
      event.preventDefault();
      activate(tabs[next], true);
    });
  });
});
