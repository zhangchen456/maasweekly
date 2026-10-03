import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { IncomingMessage } from 'node:http';
import { ProStore } from './pro-store.js';
import { AccountError } from './account-store.js';
import { proUser } from './pro-http.js';
import type { AccountConfig } from './account-http.js';
export function registerProTools(mcp: McpServer, store: ProStore, req: IncomingMessage, config: AccountConfig) {
  const output = (value: unknown) => ({content:[{type:'text' as const,text:JSON.stringify(value)}]});
  mcp.registerTool('maas_pro_catalog',{description:'审核后的专业情报目录和公开预览；全文需专业权益。',inputSchema:{}},async () => output(store.contents().map(c => ({id:c.id,title:c.title,kind:c.kind,version:c.version,preview:c.preview,period:c.period}))));
  const authenticated = () => { const u=proUser(store,req,config); if (!u) throw new AccountError(401,'unauthenticated','在客户端配置 Authorization: Bearer 凭证'); store.require(u.id); return u; };
  mcp.registerTool('maas_pro_read',{description:'读取审核后的详解、对比专题或简报，含条件、来源和更正。',inputSchema:{id:z.string().max(200)}},async ({id}) => {
    try { const u=proUser(store,req,config); return output(store.get(id,u?.id)); } catch(e) { const error=e instanceof AccountError ? e : new AccountError(503,'pro_error','暂不可用'); return {...output({code:error.code,message:error.message}),isError:true}; }
  });
  mcp.registerTool('maas_pro_reports',{description:'本人个人简报目录；提供ID时读取范围快照和最新修订。',inputSchema:{id:z.string().max(200).optional()}},async ({id}) => {
    try { const u=authenticated(); return output(id ? store.report(u.id,id) : store.reports(u.id)); } catch(e) { const error=e instanceof AccountError ? e : new AccountError(503,'pro_error','暂不可用'); return {...output({code:error.code,message:error.message}),isError:true}; }
  });
}
