import {accountApi,onAccountChange} from './account-client';
const root=document.getElementById('membership-tools');
if(root){
 const el=(id:string)=>document.getElementById(id)!;let generation=0;
 const en=document.documentElement.lang==='en';
 async function load(){const g=++generation;try{
  const m=await accountApi<any>('membership');if(g!==generation)return;root!.hidden=false;
  el('membership-watch-limit').textContent=en?`Up to ${m.limits.watches} models`:`最多 ${m.limits.watches} 个模型`;
  el('membership-schedule').textContent=m.tier==='plus'?(en?'Checked daily at 09:15 Asia/Shanghai; sent when changes exist.':'每天北京时间09:15检查，有变化时发送。'):(en?'Checked on Mondays at 09:15 Asia/Shanghai; sent when changes exist.':'每周一北京时间09:15检查，有变化时发送。');
  el('membership-cadence').textContent=m.tier==='plus'?(en?'Daily email digest':'每日邮件摘要'):(en?'Weekly email digest (Monday)':'每周邮件摘要（周一）');
  el('membership-usage').textContent=`${m.tier==='plus'?'Plus':'Free'} · ${m.usage.used} / ${m.usage.limit} queries · ${m.usage.month} (Asia/Shanghai)`;
  el('membership-transition').textContent=m.transition?(en?'Reduce your free watchlist to 3 or choose Plus. Reminders pause after the transition.':'请将免费关注调整至3个或升级Plus；过渡期后暂停提醒，关注配置保留。')+' '+new Date(m.transition.ends).toLocaleDateString():'';
  el('membership-tokens').replaceChildren();for(const token of m.tokens){if(token.revoked)continue;const p=document.createElement('p');p.textContent=token.name+' · '+new Date(token.expires).toLocaleString();const b=document.createElement('button');b.textContent=en?'Revoke':'撤销';b.onclick=async()=>{try{await accountApi('tokens/revoke',{id:token.id});await load();}catch{el('membership-secret').textContent=en?'Could not revoke; retry.':'撤销失败，请重试';}};p.append(b);el('membership-tokens').append(p);}
 }catch{if(g===generation)root!.hidden=true;}}
 el('membership-mint').onclick=async()=>{const g=generation;const b=el('membership-mint') as HTMLButtonElement;b.disabled=true;try{const v=await accountApi<{token:string}>('tokens',{name:(el('membership-token-name') as HTMLInputElement).value});if(g===generation){el('membership-secret').textContent=v.token;await load();}}catch(e){if(g===generation)el('membership-secret').textContent=(e as Error).message;}finally{b.disabled=false;}};
 onAccountChange(user=>{generation++;el('membership-secret').textContent='';root.hidden=true;if(user)void load();});
}
