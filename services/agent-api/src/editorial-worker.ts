import { ModelTaskLease, boundedModelCall } from './model-task-runtime.js';
import { pathToFileURL } from 'node:url';
import { z } from 'zod';
import { AccountStore } from './account-store.js';
import { AdminStore } from './admin-store.js';
import { EditorialStore, packageSchema } from './editorial-store.js';
import { EditorialService } from './editorial-service.js';
import { DatasetHolder } from './dataset.js';
import { MockModel, OpenAIModel, ModelFailure, modelConfigSchema, prompt, type EditorialModel, type ModelInput } from './editorial-model.js';
import { checkPackage } from './editorial-checks.js';
const curatedSchema=z.object({selectedIds:z.array(z.string()).min(1).max(100),rationale:z.string().min(1).max(4000)}).strict();
const reviewedSchema=z.object({findings:z.array(z.string().max(4000)).max(100),recommendation:z.string().min(1).max(4000)}).strict();
export class EditorialWorker {
 readonly lease:ModelTaskLease;
 constructor(readonly service:EditorialService,readonly adapter?:EditorialModel){this.lease=new ModelTaskLease(service.store.admin,'editorial_runs');}
 get owner(){return this.lease.owner;}
 get store(){return this.service.store;}
 recover(){return this.lease.recover();}
 claim(){return this.store.admin.accounts.transaction(()=>{
  const r=this.store.db.prepare("SELECT * FROM editorial_runs WHERE state='queued' AND availableAt<=? ORDER BY createdAt,id LIMIT 1").get(this.store.now);if(!r)return null;
  if(r.stage!=='prepare'&&Number(this.store.db.prepare("SELECT coalesce(sum(attempt),0) n FROM editorial_runs WHERE issueId=? AND stage!='prepare'").get(String(r.issueId))!.n)>=30){this.store.db.prepare("UPDATE editorial_runs SET state='failed',errorCode='call_limit',version=version+1,finishedAt=? WHERE id=?").run(this.store.now,String(r.id));return null;}
  this.store.db.prepare("UPDATE editorial_runs SET state='running',leaseOwner=?,leaseUntil=?,fencingVersion=fencingVersion+1,version=version+1,attempt=attempt+1,startedAt=? WHERE id=? AND state='queued'").run(this.owner,this.store.now+300000,this.store.now,String(r.id));return this.store.run(String(r.id));
 });}
 heartbeat(id:string,fence:number){return this.lease.heartbeat(id,fence);}
 active(id:string,fence:number){return this.lease.active(id,fence);}
 finish(id:string,fence:number,state:string,result:unknown,errorCode:string|null){
  if(!this.active(id,fence))return false;const r=this.store.run(id),i=this.store.issue(String(r.issueId)),payload=JSON.parse(String(r.payload));
  if(payload.snapshotHash!==i.inputHash){state='cancelled';errorCode='input_changed';}
  this.store.db.prepare('UPDATE editorial_runs SET state=?,result=?,errorCode=?,version=version+1,finishedAt=?,leaseUntil=0 WHERE id=?').run(state,result===null?null:JSON.stringify(result),errorCode,this.store.now,id);return true;
 }
 async once(){this.recover();const r=this.claim();if(!r)return false;const id=String(r.id),fence=Number(r.fencingVersion),config=modelConfigSchema.parse(JSON.parse(String(r.config))),payload=JSON.parse(String(r.payload)),input=payload as ModelInput;
  const timer=setInterval(()=>this.heartbeat(id,fence),30000);timer.unref();
  try {
   if(input.stage==='prepare'){this.store.admin.accounts.transaction(()=>this.finish(id,fence,'succeeded',{evidenceCount:input.inputs.length,snapshotHash:payload.snapshotHash},null));return true;}
   if(input.stage==='analyze'){const selected=new Set((input.upstream as {selectedIds:string[]}).selectedIds);input.inputs=input.inputs.filter(e=>selected.has(e.id));}
   if(Buffer.byteLength(prompt(input))>config.maxInputTokens)throw new ModelFailure('input_limit');
   const model=this.adapter??(config.adapter==='mock'?new MockModel():new OpenAIModel());
   // Timeouts always remain uncertain; an adapter that ignores abort cannot write late results.
   const output=await boundedModelCall(model,input,config);
   this.store.admin.accounts.transaction(()=>{
    // Preserve known incurred usage even after cancellation/recovery; never commit stale content.
    const current=this.store.run(id),usage=JSON.parse(String(current.usage));usage.push({attempt:r.attempt,fencingVersion:fence,inputTokens:output.inputTokens,outputTokens:output.outputTokens,actualCost:output.actualCost,requestId:output.requestId,adapter:config.adapter});this.store.db.prepare('UPDATE editorial_runs SET usage=?,actualCost=? WHERE id=?').run(JSON.stringify(usage),output.actualCost===null?(current.actualCost??null):Number(current.actualCost??0)+output.actualCost,id);
   });
   this.store.admin.accounts.transaction(()=>{
    if(!this.active(id,fence))return;
    if(output.inputTokens>config.maxInputTokens||output.outputTokens>config.maxOutputTokens){this.finish(id,fence,'failed',null,'token_limit');return;}
    if(input.stage==='curate'){const parsed=curatedSchema.safeParse(output.output);if(!parsed.success||parsed.data.selectedIds.some(e=>!input.inputs.some(ref=>ref.id===e)))throw new ModelFailure('invalid_selection');this.finish(id,fence,'succeeded',parsed.data,null);}
    else if(input.stage==='analyze'){
     const pack=packageSchema.safeParse(output.output);if(!pack.success)throw new ModelFailure('invalid_schema');const i=this.store.issue(String(r.issueId));if(payload.snapshotHash!==i.inputHash||payload.baseRevision!==i.currentRevision){this.finish(id,fence,'cancelled',null,'input_changed');return;}
     const checks=checkPackage(pack.data,i,this.store.inputs(i.id));if(checks.blocking.length){this.finish(id,fence,'needs_review',{checks,output:pack.data},'fact_check_failed');return;}
     const saved=this.service.saveRevision(i.id,pack.data,'worker:'+this.owner,id);this.finish(id,fence,'succeeded',saved,null);
    }else {const parsed=reviewedSchema.safeParse(output.output);if(!parsed.success)throw new ModelFailure('invalid_review_schema');this.finish(id,fence,'succeeded',{...parsed.data,machine:checkPackage(packageSchema.parse(input.upstream),this.store.issue(String(r.issueId)),this.store.inputs(String(r.issueId)))},null);}
   });
  }catch(error){
   const failure=error instanceof ModelFailure?error:new ModelFailure('invalid_output');
   this.store.admin.accounts.transaction(()=>{if(!this.active(id,fence))return;const current=this.store.run(id);const usage=JSON.parse(String(current.usage));usage.push({attempt:current.attempt,error:failure.code,uncertain:failure.uncertain,actualCost:null,at:this.store.now});this.store.db.prepare('UPDATE editorial_runs SET usage=? WHERE id=?').run(JSON.stringify(usage),id);
    if(failure.retryable&&Number(current.attempt)<3){this.store.db.prepare("UPDATE editorial_runs SET state='queued',leaseUntil=0,version=version+1,errorCode=?,availableAt=? WHERE id=?").run(failure.code,this.store.now+Math.pow(2,Number(current.attempt))*1000,id);}
    else this.finish(id,fence,failure.uncertain?'needs_review':'failed',null,failure.code);
   });
  }finally{clearInterval(timer);}
  return true;
 }
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 if(!process.env.MAAS_ACCOUNT_DB||!process.env.PUBLIC_DATA_ROOT)throw new Error('MAAS_ACCOUNT_DB and PUBLIC_DATA_ROOT required');
 const accounts=new AccountStore(process.env.MAAS_ACCOUNT_DB),holder=new DatasetHolder(process.env.PUBLIC_DATA_ROOT);await holder.reloadAsync();
 const worker=new EditorialWorker(new EditorialService(new EditorialStore(new AdminStore(accounts)),holder));let stopped=false;let wake:(()=>void)|null=null;
 for(const signal of ['SIGINT','SIGTERM'] as const)process.on(signal,()=>{stopped=true;wake?.();});
 try{do{await holder.reloadAsync();const worked=await worker.once();if(process.argv.includes('--once'))break;if(!worked&&!stopped)await new Promise<void>(resolve=>{const timer=setTimeout(resolve,1000);wake=()=>{clearTimeout(timer);resolve();};});}while(!stopped);}finally{holder.close();accounts.close();}
}
