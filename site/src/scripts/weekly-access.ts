import {localizedWeeklyHtml} from '../lib/weekly-body-locale';
import {currentAccount,onAccountChange,openAccountLogin} from './account-client';
const gate=document.querySelector<HTMLElement>('[data-weekly-gate]');
if(gate){
 const button=document.getElementById('weekly-enable') as HTMLButtonElement,status=document.getElementById('weekly-status')!,body=document.getElementById('weekly-content')!;
 let generation=0,pending=false,retry=false;
 async function load(){retry=false;const version=++generation;body.replaceChildren();body.hidden=true;gate!.hidden=false;button.disabled=true;
  if(!currentAccount()){button.disabled=false;button.textContent='登录后查看 Plus';status.textContent='登录后可继续阅读。';return;}
  try{
   const me=await fetch('/api/pro/me',{cache:'no-store',credentials:'same-origin'});if(!me.ok)throw new Error('无法查询权益，请重试。');const p=await me.json();if(version!==generation)return;
   if(p.entitlement.status!=='active'){button.disabled=p.entitlement.status==='revoked';button.textContent=button.disabled?'暂不可开通':'查看 Plus 订阅';status.textContent='当前为 Free，可阅读摘要和公开样例。';if(pending&&!button.disabled){pending=false;await activate();}return;}
   pending=false;const r=await fetch('/api/pro/weekly/'+encodeURIComponent(gate!.dataset.weeklyId!),{cache:'no-store',credentials:'same-origin'});if(!r.ok)throw new Error('全文暂时不可用，请刷新重试。');const html=await r.text();if(version!==generation)return;body.innerHTML=localizedWeeklyHtml(html,document.documentElement.lang==='en'?'en':'zh');body.hidden=false;gate!.hidden=true;
  }catch(e){if(version!==generation)return;retry=true;status.textContent=e instanceof Error?e.message:'加载失败，请重试。';button.textContent='重试';button.disabled=false;}
 }
 async function activate(){location.assign(document.documentElement.lang==='en'?'/en/subscription/':'/subscription/');}
 button.onclick=()=>{if(!currentAccount()){pending=true;openAccountLogin();return;}if(retry)void load();else void activate();};
 onAccountChange(()=>{void load();});
}
