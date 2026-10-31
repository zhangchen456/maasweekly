import {accountApi,currentAccount} from './account-client';
export function recordWorkspaceResult(event:'comparison_completed'|'cost_estimate_completed_v2') {
 try {
  if(navigator.doNotTrack==='1'||localStorage.getItem('umami.disabled'))return;
  document.dispatchEvent(new CustomEvent('maas:workspace-result',{detail:{event}}));
  if(currentAccount())void accountApi('usage',{event},true).catch(()=>{});
 }catch{/* Optional statistics must never interrupt the workspace. */}
}
