import {currentAccount,onAccountChange,openAccountLogin} from './account-client';
const gate=document.querySelector<HTMLElement>('[data-weekly-gate]');
if(gate){
 const button=document.getElementById('weekly-enable') as HTMLButtonElement,status=document.getElementById('weekly-status')!,body=document.getElementById('weekly-content')!;
 let generation=0,pending=false;
 async function load(){const version=++generation;body.replaceChildren();body.hidden=true;gate!.hidden=false;button.disabled=true;
  if(!currentAccount()){button.disabled=false;button.textContent='登录并免费开启 Plus';status.textContent='登录后可继续阅读。';return;}
  try{
   const me=await fetch('/api/pro/me',{cache:'no-store',credentials:'same-origin'});if(!me.ok)throw new Error('无法查询权益，请重试。');const p=await me.json();if(version!==generation)return;
   if(p.entitlement.status!=='active'){button.disabled=!p.betaAvailable||p.entitlement.status==='revoked';button.textContent=button.disabled?'暂不可开通':'免费开启 Plus，继续阅读';status.textContent='当前为 Free，可阅读摘要和公开样例。';if(pending&&!button.disabled){pending=false;await activate();}return;}
   pending=false;const r=await fetch('/api/pro/weekly/'+encodeURIComponent(gate!.dataset.weeklyId!),{cache:'no-store',credentials:'same-origin'});if(!r.ok)throw new Error('全文暂时不可用，请刷新重试。');const html=await r.text();if(version!==generation)return;body.innerHTML=html;body.hidden=false;gate!.hidden=true;
  }catch(e){if(version!==generation)return;status.textContent=e instanceof Error?e.message:'加载失败，请重试。';button.textContent='重试';button.disabled=false;}
 }
 async function activate(){const version=generation;button.disabled=true;try{const r=await fetch('/api/pro/beta',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:'{}'});const p=await r.json();if(version!==generation)return;if(!r.ok)throw new Error(p.message);await load();}catch(e){if(version!==generation)return;button.disabled=false;status.textContent=e instanceof Error?e.message:'开通失败，请重试。';}}
 button.onclick=()=>{if(!currentAccount()){pending=true;openAccountLogin();return;}if(button.textContent==='重试')void load();else void activate();};
 onAccountChange(()=>{void load();});
}
