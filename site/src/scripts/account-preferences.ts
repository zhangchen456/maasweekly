import { savedState } from './account-client';
const save = savedState('appearance', { theme: 'light' }, value => {
  const theme = ['light', 'dark'].includes(value.theme) ? value.theme : 'light';
  document.documentElement.dataset.theme = theme;
  document.dispatchEvent(new CustomEvent('maas:appearance-restored', { detail: theme }));
});
document.addEventListener('maas:theme-change', event => save({ theme: (event as CustomEvent<string>).detail }));
