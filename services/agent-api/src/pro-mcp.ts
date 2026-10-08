import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import type { IncomingMessage } from 'node:http';
import { ProStore } from './pro-store.js';
import { AccountError } from './account-store.js';
import { proUser } from './pro-http.js';
import type { DatasetHolder } from './dataset.js';
import type { AccountConfig } from './account-http.js';
export function registerProTools(mcp: McpServer, store: ProStore, req: IncomingMessage, config: AccountConfig, holder: DatasetHolder) {
  const output = (value: unknown) => ({content:[{type:'text' as const,text:JSON.stringify(value)}]});
  mcp.registerTool('maas_pro_catalog',{description:'审核后的专业情报目录和公开预览；全文需专业权益。',inputSchema:{}},async () => output(store.contents().map(c => ({id:c.id,title:c.title,kind:c.kind,version:c.version,preview:c.preview,period:c.period}))));
  const authenticated = () => { const u=proUser(store,req,config); if (!u) throw new AccountError(401,'unauthenticated','在客户端配置 Authorization: Bearer 凭证'); store.require(u.id); return u; };
  mcp.registerTool('maas_pro_read',{description:'读取审核后的详解、对比专题或简报，含条件、来源和更正。',inputSchema:{id:z.string().max(200)}},async ({id}) => {
    try { const u=proUser(store,req,config); const c=store.get(id,u?.id);store.event(c.sample?'sample_read':'content_read',c.id,u?.id);store.event('agent_tool_success','maas_pro_read',u?.id);return output(c); } catch(e) { const error=e instanceof AccountError ? e : new AccountError(503,'pro_error','暂不可用'); return {...output({code:error.code,message:error.message}),isError:true}; }
  });
  mcp.registerTool('maas_pro_weekly', {
    description:'读取深度周报全文，包括详解、趋势、关注点与来源。省略 id 读取最新一期；需要有效 Plus 通用凭证。',
    inputSchema:{id:z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional()},
  },async ({id}) => {
    try {
      const u=authenticated(), ds=holder.current;
      if (!ds) throw new AccountError(503,'data_unavailable','周报数据暂不可用');
      const weekly=id ? ds.weekly.find(w=>w.id===id) : ds.weeklyDescending[0];
      if (!weekly) throw new AccountError(404,'not_found','周报不存在');
      store.event('agent_tool_success','maas_pro_weekly',u.id);
      store.event('weekly_read',weekly.id,u.id);
      return output({datasetVersion:ds.version,dataThrough:ds.dataThrough,weekly,url:`${config.origin}/weekly/${weekly.id}/`});
    } catch(e) {
      const error=e instanceof AccountError ? e : new AccountError(503,'pro_error','暂不可用');
      return {...output({code:error.code,message:error.message}),isError:true};
    }
  });
  mcp.registerTool('maas_pro_reports',{description:'本人个人简报目录；提供ID时读取范围快照和最新修订。',inputSchema:{id:z.string().max(200).optional()}},async ({id}) => {
    try { const u=authenticated(); const value=id ? store.report(u.id,id) : store.reports(u.id);if(id)store.event('report_read',id,u.id);store.event('agent_tool_success','maas_pro_reports',u.id);return output(value); } catch(e) { const error=e instanceof AccountError ? e : new AccountError(503,'pro_error','暂不可用'); return {...output({code:error.code,message:error.message}),isError:true}; }
  });
}
