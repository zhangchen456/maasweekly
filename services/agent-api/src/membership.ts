/** Account-level membership policy. Disabled until the complete release is verified. */
import {AsyncLocalStorage} from 'node:async_hooks';
import {createHash,randomBytes,randomUUID} from 'node:crypto';
import type {IncomingMessage} from 'node:http';
import {AccountError, type AccountStore} from './account-store.js';
import type {ProStore} from './pro-store.js';
export type Tier='visitor'|'free'|'plus';
export interface Access {tier:Tier; userId?:string; machine?:boolean}
export const MEMBERSHIP_LIMITS={visitor:{historyDays:7,compare:1,watches:0,queries:0},free:{historyDays:30,compare:3,watches:3,queries:100},plus:{historyDays:null,compare:10,watches:50,queries:3000}} as const;
export const membershipEnabled=()=>process.env.MAAS_MEMBERSHIP_V2==='1';
export const membershipContext=new AsyncLocalStorage<Access>();
export const currentAccess=()=>membershipContext.getStore();
export function historyCutoff(dataThrough:string, tier:Tier){
 const days=MEMBERSHIP_LIMITS[tier].historyDays;if(days===null)return null;
 const date=new Date(dataThrough.slice(0,10)+'T00:00:00+08:00');date.setUTCDate(date.getUTCDate()-days+1);
 return new Date(date.getTime()+8*3600000).toISOString().slice(0,10);
}
export function historyAllowed(date:string,dataThrough:string){const a=currentAccess();if(!a)return true;const cutoff=historyCutoff(dataThrough,a.tier);return !cutoff||date.slice(0,10)>=cutoff;}
const hash=(s:string)=>createHash('sha256').update(s).digest('hex');
export class Membership {
 constructor(readonly accounts:AccountStore,readonly pro:ProStore,readonly secure:boolean){
  accounts.db.exec(`CREATE TABLE IF NOT EXISTS membership_tokens(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,hash TEXT UNIQUE NOT NULL,created INTEGER NOT NULL,expires INTEGER NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS membership_usage(userId TEXT NOT NULL,month TEXT NOT NULL,used INTEGER NOT NULL,PRIMARY KEY(userId,month));
   CREATE TABLE IF NOT EXISTS membership_transition(userId TEXT PRIMARY KEY,started INTEGER NOT NULL);`);
  accounts.watchLimit=id=>this.limits(id).watches;
  accounts.digestEligible=id=>this.tier(id)==='plus'||new Date(accounts.now()+8*3600000).getUTCDay()===1;
  for(const row of accounts.db.prepare('SELECT userId FROM watches GROUP BY userId HAVING COUNT(*)>3').all())accounts.db.prepare('INSERT OR IGNORE INTO membership_transition VALUES(?,?)').run(String(row.userId),accounts.now());
  accounts.effectiveWatches=id=>this.transition(id)?.paused?[]:accounts.watches(id);
 }
 transition(id:string){if(this.tier(id)==='plus'||this.accounts.watches(id).length<=3)return null;const row=this.accounts.db.prepare('SELECT started FROM membership_transition WHERE userId=?').get(id);if(!row)return null;const ends=Number(row.started)+14*86400000;return {ends,paused:this.accounts.now()>=ends,message:'请将免费关注调整至3个，或升级Plus。过渡期后暂停超额名单的提醒；关注配置保留。'};}
 tier(id?:string):Tier{return !id?'visitor':this.pro.entitlement(id).status==='active'?'plus':'free';}
 limits(id?:string){return MEMBERSHIP_LIMITS[this.tier(id)];}
 access(req:IncomingMessage):Access{
  if(req.headers.authorization){const m=/^Bearer ([A-Za-z0-9_-]{43})$/.exec(req.headers.authorization);if(!m)throw new AccountError(401,'invalid_token','访问凭证无效');
   const row=this.accounts.db.prepare('SELECT userId FROM membership_tokens WHERE hash=? AND revoked=0 AND expires>?').get(hash(m[1]!),this.accounts.now());
   if(!row){const legacy=this.pro.authenticate(m[1]!, 'api');return {userId:legacy.id,tier:this.tier(legacy.id),machine:true};}
   const userId=String(row.userId);return {userId,tier:this.tier(userId),machine:true};}
  const name=this.secure?'__Host-maas_session':'maas_session';const cookie=(req.headers.cookie??'').split(';').map(v=>v.trim()).find(v=>v.startsWith(name+'='))?.slice(name.length+1)??'';
  const user=this.accounts.user(cookie);return {tier:this.tier(user?.id),userId:user?.id};
 }
 tokens(id:string){return this.accounts.db.prepare('SELECT id,name,created,expires,revoked FROM membership_tokens WHERE userId=? ORDER BY created DESC LIMIT 100').all(id);}
 mint(id:string,name:string){if(!name.trim()||name.length>60)throw new AccountError(400,'invalid_name','凭证名称需为1–60个字符');
  if(Number(this.accounts.db.prepare('SELECT COUNT(*) n FROM membership_tokens WHERE userId=? AND revoked=0 AND expires>?').get(id,this.accounts.now())?.n)>=10)throw new AccountError(400,'token_limit','请先撤销不用的凭证');
  const token=randomBytes(32).toString('base64url'),tokenId=randomUUID();this.accounts.db.prepare('INSERT INTO membership_tokens VALUES(?,?,?,?,?,?,0)').run(tokenId,id,name.trim(),hash(token),this.accounts.now(),this.accounts.now()+30*86400000);return {id:tokenId,token};}
 revoke(id:string,tokenId:string){this.accounts.db.prepare('UPDATE membership_tokens SET revoked=1 WHERE userId=? AND id=?').run(id,tokenId);}
 usage(id:string){const month=new Date(this.accounts.now()+8*3600000).toISOString().slice(0,7),limit=this.limits(id).queries;const used=Number(this.accounts.db.prepare('SELECT used FROM membership_usage WHERE userId=? AND month=?').get(id,month)?.used??0);const [year,monthNumber]=month.split('-').map(Number);const resetsAt=new Date(Date.UTC(year!,monthNumber!,1)-8*3600000).toISOString();return {month,used,limit,resetsAt};}
 reserve(id:string){return this.accounts.transaction(()=>{const u=this.usage(id);if(u.used>=u.limit)throw new AccountError(429,'query_quota_exceeded','本月查询额度已用完，请下月重试或升级 Plus');this.accounts.db.prepare('INSERT INTO membership_usage VALUES(?,?,1) ON CONFLICT(userId,month) DO UPDATE SET used=used+1').run(id,u.month);return ()=>{this.accounts.db.prepare('UPDATE membership_usage SET used=MAX(0,used-1) WHERE userId=? AND month=?').run(id,u.month);};});}
}
