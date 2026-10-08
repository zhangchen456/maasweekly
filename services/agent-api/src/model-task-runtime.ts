import { randomUUID } from 'node:crypto';
import type { AdminStore } from './admin-store.js';
import { ModelFailure, type EditorialModel, type ModelInput, type ModelConfig } from './editorial-model.js';
/** Shared T03 transport timeout and task lease/fencing primitives; no provider retry inside transport. */
export async function boundedModelCall(model:EditorialModel,input:ModelInput,config:ModelConfig){let timeout:ReturnType<typeof setTimeout>|undefined;return Promise.race([model.call(input,config),new Promise<never>((_,reject)=>{timeout=setTimeout(()=>reject(new ModelFailure('provider_outcome_unknown',false,true)),config.timeoutMs);timeout.unref();})]).finally(()=>{if(timeout)clearTimeout(timeout);});}
export class ModelTaskLease {
 readonly owner=randomUUID();
 constructor(readonly admin:AdminStore,readonly table:'editorial_runs'|'diagnostic_runs'){}
 get now(){return this.admin.accounts.now();}
 recover(){return this.admin.accounts.transaction(()=>this.admin.db.prepare(`UPDATE ${this.table} SET state='needs_review',errorCode='lease_expired_outcome_unknown',fencingVersion=fencingVersion+1,version=version+1,finishedAt=? WHERE state='running' AND leaseUntil<=?`).run(this.now,this.now).changes);}
 heartbeat(id:string,fence:number){return this.admin.db.prepare(`UPDATE ${this.table} SET leaseUntil=? WHERE id=? AND state='running' AND leaseOwner=? AND fencingVersion=? AND leaseUntil>?`).run(this.now+300000,id,this.owner,fence,this.now).changes===1;}
 active(id:string,fence:number){const r=this.admin.db.prepare(`SELECT * FROM ${this.table} WHERE id=?`).get(id);return Boolean(r&&r.state==='running'&&r.leaseOwner===this.owner&&r.fencingVersion===fence&&Number(r.leaseUntil)>this.now);}
}
