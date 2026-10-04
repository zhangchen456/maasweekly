import {onAccountChange} from './account-client';
let generation=0;
onAccountChange(async me=>{
 const version=++generation;
 const set=(value:string)=>document.querySelectorAll<HTMLElement>('[data-account-plan]').forEach(el=>{el.textContent=value;});
 set(me?'—':'Free');if(!me)return;
 try{const response=await fetch('/api/pro/me',{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw new Error();const value=await response.json();if(version===generation)set(value.entitlement.status==='active'?'Plus':'Free');}
 catch{if(version===generation)set(document.documentElement.lang==='en'?'Unavailable':'暂不可用');}
});
