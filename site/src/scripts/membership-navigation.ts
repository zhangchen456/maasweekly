import {onAccountChange} from './account-client';
const key='maas-membership-return';
const valid=(value:string)=>{try{const u=new URL(value,location.origin);return u.origin===location.origin&&/^\/(?:en\/)?(?:pricing|changes|model)(?:\/|$)/.test(u.pathname)?u.pathname+u.search+u.hash:null;}catch{return null;}};
document.addEventListener('click',event=>{const a=(event.target as HTMLElement).closest<HTMLAnchorElement>('a[href]');if(!a)return;const u=new URL(a.href,location.origin);if(u.origin===location.origin&&/^\/(?:en\/)?subscription(?:\/|$)/.test(u.pathname)){const back=valid(location.href);if(back)try{sessionStorage.setItem(key,back);}catch{}}});
if(/^\/(?:en\/)?subscription(?:\/|$)/.test(location.pathname)){try{const back=valid(sessionStorage.getItem(key)??'');if(back){const a=document.createElement('a');a.href=back;a.textContent=document.documentElement.lang==='en'?'Return to your task':'返回刚才的查询或计算';document.querySelector('main')?.prepend(a);}}catch{}}
onAccountChange(()=>{document.dispatchEvent(new CustomEvent('maas:membership-refresh'));});
