import { randomUUID } from 'node:crypto';
import { type AdminCommand,adminText } from './admin-store.js';
export function cliCommand(args:string[],action:string,targetType:string,targetId:string,input:Record<string,unknown>,currentVersion:()=>number,actor?:string,reason?:string):AdminCommand {
  const flag=(name:string)=>{const i=args.indexOf('--'+name);return i<0?undefined:args[i+1];};
  const raw=flag('expected-version');if(!raw||!/^\d+$/.test(raw)||!Number.isSafeInteger(Number(raw)))throw new Error('必须提供 --expected-version N；先读取当前版本，冲突后重新检查');
  return {actor:{type:'cli',id:adminText(flag('actor')??actor,'操作者')},action,targetType,targetId,input,reason:adminText(flag('reason')??reason,'原因',1000),expectedVersion:Number(raw),currentVersion,idempotencyKey:adminText(flag('key')??randomUUID(),'幂等键',128),requestId:randomUUID()};
}
