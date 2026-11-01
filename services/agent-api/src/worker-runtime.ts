import { realpathSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { dirname, join, basename } from 'node:path';

/** TERM closes the claim loop, but never aborts a task or its fenced completion. */
export async function runWorker(once:()=>Promise<boolean>, options:{name:string;prepare?:()=>Promise<unknown>;single?:boolean;receipt?:string}) {
 let stopped=false,wake:(()=>void)|undefined,lastPhase='';
 const code=basename(dirname(realpathSync(process.cwd())));
 const receipt=options.receipt ?? (process.env.MAAS_ACCOUNT_DB ? join(process.env.MAAS_WORKER_STATE_DIR ?? '/srv/maasweekly/shared/state',`${options.name}-worker.json`) : undefined);
 const report=(phase:string)=>{if(receipt&&lastPhase!==phase){mkdirSync(dirname(receipt),{recursive:true});const temp=receipt+'.'+process.pid;writeFileSync(temp,JSON.stringify({protocol:1,pid:process.pid,code,phase}));renameSync(temp,receipt);lastPhase=phase;}};
 const stop=()=>{stopped=true;report('draining');wake?.();};
 process.on('SIGTERM',stop);process.on('SIGINT',stop);
 try {
  while(!stopped){
   await options.prepare?.();
   if(stopped)break;
   report('ready');
   const worked=await once();
   if(options.single)break;
   if(!worked&&!stopped)await new Promise<void>(resolve=>{const timer=setTimeout(()=>{wake=undefined;resolve();},1000);wake=()=>{clearTimeout(timer);wake=undefined;resolve();};});
  }
 } finally {process.off('SIGTERM',stop);process.off('SIGINT',stop);report('stopped');}
}
