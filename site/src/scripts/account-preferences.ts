import { savedState } from './account-client';
const initialTheme = document.documentElement.dataset.themePreference ?? 'system';
const save = savedState('appearance', { theme: initialTheme }, value => {
  const theme = ['system', 'light', 'dark'].includes(value.theme) ? value.theme : 'system';
  document.dispatchEvent(new CustomEvent('maas:appearance-restored', { detail: theme }));
});
document.addEventListener('maas:theme-change', event => save({ theme: (event as CustomEvent<string>).detail }));
