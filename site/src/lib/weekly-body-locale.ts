/** The input has already passed the authenticated weekly-body endpoint. */
export function localizedWeeklyHtml(html:string,locale:'zh'|'en') {
  const parsed=document.createElement('template');parsed.innerHTML=html;
  return parsed.content.querySelector<HTMLElement>(`[data-weekly-locale="${locale}"]`)?.innerHTML ?? html;
}
