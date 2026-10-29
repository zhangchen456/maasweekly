/** Bound the rendered response; cache only public GETs under their data version. */
import {createHash} from 'node:crypto';
import { IncomingMessage, type ServerResponse } from 'node:http';
import { Socket } from 'node:net';
import { Writable } from 'node:stream';
import { finished } from 'node:stream/promises';
import type { DatasetHolder } from './dataset.js';
import type { SiteRuntime } from './site-runtime.js';
export type AstroHandler=(req:IncomingMessage,res:ServerResponse,next?:()=>void,locals?:Record<string,unknown>)=>Promise<void>;
export interface Rendered {status:number;headers:Record<string,string|string[]|number>;body:Buffer}
export async function capturePage(handler:AstroHandler,url:string,origin:string,internal=false):Promise<Rendered> {
  const target=new URL(origin),socket=new Socket();
  const req=new IncomingMessage(socket);req.method='GET';req.url=url;req.headers={host:target.host};
  // Do not forward user-controlled host, cookies or credentials to public page templates.
  const chunks:Buffer[]=[];let bytes=0;
  const response=new Writable({write(chunk,_encoding,callback){
    bytes+=Buffer.byteLength(chunk);
    if(bytes>8*1024*1024){callback(new Error('render budget exceeded'));return;}
    chunks.push(Buffer.from(chunk));callback();
  }}) as Writable & {statusCode:number;headersSent:boolean;req:IncomingMessage;headers:Rendered['headers'];writeHead:(status:number,headers?:Rendered['headers'])=>void};
  response.req=req;response.statusCode=200;response.headersSent=false;response.headers={};
  response.writeHead=(status,headers={})=>{response.statusCode=status;response.headers=headers;response.headersSent=true;};
  const done=finished(response);void done.catch(()=>{});
  try {
    await handler(req,response as unknown as ServerResponse,()=>{response.writeHead(404);response.end('Not found');},internal?{internalWeekly:true}:{});
    if(!response.writableEnded)throw new Error('incomplete render');
    await done;
    return {status:response.statusCode,headers:response.headers,body:Buffer.concat(chunks)};
  } finally {response.destroy();socket.destroy();}
}
export function createSiteHandler(holder:DatasetHolder,runtime:SiteRuntime,handler:AstroHandler,origin:string) {
  const cache=new Map<string,Rendered>();let cacheBytes=0;
  const inFlight=new Map<string,Promise<Rendered>>();let activeRenders=0;
  const render=async(url:string,internal=false)=>{
    const dataset=holder.current;if(!dataset)throw new Error('data unavailable');
    const key=runtime.run(dataset,()=>runtime.bridge.publicationKey())+':'+url;
    if(!internal&&cache.has(key)){const hit=cache.get(key)!;cache.delete(key);cache.set(key,hit);return hit;}
    if(!internal&&inFlight.has(key))return inFlight.get(key)!;
    if(activeRenders>=8)throw new Error('render capacity');
    activeRenders++;
    const task=Promise.resolve().then(()=>runtime.run(dataset,()=>capturePage(handler,url,origin,internal)));
    if(!internal)inFlight.set(key,task);
    try {
      const value=await task;
      const headers=Object.fromEntries(Object.entries(value.headers).map(([k,v])=>[k.toLowerCase(),v]));
      if(!internal&&value.status===200&&!headers['set-cookie']&&!/private|no-store/i.test(String(headers['cache-control']??''))){
        while(cache.size>=64||cacheBytes+value.body.length>16*1024*1024){
          const oldest=cache.keys().next().value;if(oldest===undefined)break;
          cacheBytes-=cache.get(oldest)!.body.length;cache.delete(oldest);
        }
        cache.set(key,value);cacheBytes+=value.body.length;
      }
      return value;
    } finally {activeRenders--;if(!internal)inFlight.delete(key);}
  };
  return {
    weekly:async(id:string)=>{
      if(!/^\d{4}-\d{2}-\d{2}$/.test(id))return null;
      const result=await render('/_internal/weekly-body/'+id+'/',true);
      if(result.status===404)return null;
      if(result.status!==200)throw new Error('private report render failed');
      return result.body.toString('utf8');
    },
    handle:async(req:IncomingMessage,res:ServerResponse)=>{
      const send=(status:number,body:string)=>{res.writeHead(status,{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'});res.end(body);};
      const url=req.url??'/';let parsed:URL;
      try{parsed=new URL(url,origin);decodeURIComponent(parsed.pathname);}catch{send(400,'Bad request');return;}
      // Only origin-form URLs and public pages are accepted here. Internal routes need trusted locals.
      if(!url.startsWith('/')||url.startsWith('//')||parsed.pathname.startsWith('/_internal')||parsed.pathname.startsWith('/_astro/')){send(404,'Not found');return;}
      if(!['GET','HEAD'].includes(req.method??'')){send(405,'Method not allowed');return;}
      if(url.length>8192){send(414,'URI too long');return;}
      try {
        // Query strings are used by client scripts; templates depend only on the pathname.
        const result=await render(parsed.pathname);
        if(result.status>=500)throw new Error('render unavailable');
        const etag='\"'+createHash('sha256').update(result.body).digest('hex')+'\"';
        if(result.status===200&&(req.headers['if-none-match']??'').split(',').map(s=>s.trim()).some(s=>s===etag||s==='W/'+etag||s==='*')){res.writeHead(304,{'ETag':etag,'Cache-Control':'no-cache'});res.end();return;}
        res.writeHead(result.status,{...result.headers,'ETag':etag,'Cache-Control':'no-cache','X-Content-Type-Options':'nosniff',
          'Content-Length':result.body.length});
        res.end(req.method==='HEAD'?undefined:result.body);
      }catch{send(503,'Page temporarily unavailable');}
    },
  };
}
