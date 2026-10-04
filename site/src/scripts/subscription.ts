import {currentAccount,onAccountChange,openAccountLogin} from './account-client';
const root=document.querySelector<HTMLElement>('[data-subscription]');
if(root){
 const en=root.dataset.locale==='en',t=(zh:string,english:string)=>en?english:zh;
 const button=document.getElementById('subscription-plus') as HTMLButtonElement;
 const status=document.getElementById('subscription-status')!;
 let generation=0,active=false,pendingLogin=false,available=true;
 async function activate(){
  const version=generation;button.disabled=true;
  try{const r=await fetch('/api/pro/beta',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'});const p=await r.json();if(version!==generation)return;if(!r.ok)throw new Error(p.message);pendingLogin=false;await load();}
  catch(error){if(version===generation){button.disabled=false;status.textContent=error instanceof Error?error.message:t('开通失败，请重试。','Could not activate. Try again.');}}
 }
 async function load(){
  const version=++generation;active=false;available=true;button.disabled=Boolean(currentAccount());button.textContent=t('免费开启 Plus','Enable Plus for free');
  const free=root!.querySelector<HTMLElement>('[data-current-free]')!,plus=root!.querySelector<HTMLElement>('[data-current-plus]')!,label=root!.querySelector<HTMLElement>('[data-plus-label]')!;
  free.hidden=Boolean(currentAccount());plus.hidden=true;label.hidden=false;
  if(!currentAccount()){status.textContent=t('登录后即可免费开启 Plus 公测。','Sign in to enable the free Plus beta.');return;}
  try{const r=await fetch('/api/pro/me',{cache:'no-store',credentials:'same-origin'});if(!r.ok)throw new Error();const p=await r.json();if(version!==generation)return;
   active=p.entitlement.status==='active';available=p.betaAvailable&&p.entitlement.status!=='revoked';button.disabled=!active&&!available;free.hidden=active;plus.hidden=!active;label.hidden=active;
   button.textContent=active?t('进入 Plus 工作空间','Open Plus workspace'):available?t('免费开启 Plus','Enable Plus for free'):t('暂不可开通','Activation unavailable');
   status.textContent=active?(p.entitlement.source==='beta'?t('Plus 公测已开启 · 免费体验，无自动扣款。','Plus beta enabled · Free, with no automatic charges.'):t(`Plus 已生效${p.entitlement.ends?' · 服务截至 '+new Date(p.entitlement.ends).toLocaleDateString():''}`,`Plus active${p.entitlement.ends?' · Until '+new Date(p.entitlement.ends).toLocaleDateString():''}`)):available?t('当前套餐：Free · 可免费开启 Plus 公测。','Current plan: Free · Enable Plus beta for free.'):t('当前暂不可开启 Plus 公测。','Plus beta activation is currently unavailable.');
   if(pendingLogin){pendingLogin=false;if(!active&&available)await activate();}
  }catch{if(version!==generation)return;button.disabled=true;status.textContent=t('暂时无法查询权益，请刷新重试。','Could not load your plan. Please refresh.');}
 }
 onAccountChange(()=>{void load();});
 button.onclick=()=>{if(active){location.assign('/pro/');return;}if(!currentAccount()){pendingLogin=true;openAccountLogin();return;}if(available)void activate();};
}
