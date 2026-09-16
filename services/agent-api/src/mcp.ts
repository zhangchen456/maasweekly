/**
 * mcp.ts：Streamable HTTP MCP 传输层（Task 04 M4）。
 *
 * 流水线：POST-only → 独立限流（不消耗 REST 匿名桶）→ Origin 校验 →
 * 自读 body（上限 413）→ 每请求全新 McpServer + stateless transport →
 * transport.handleRequest(req, res, parsedBody)。所有响应 no-store。
 *
 * SDK 内建协议校验（不重复造）：Accept 406 / Content-Type 415 /
 * 畸形 JSON-RPC -32600。stateless 模式下每请求独立，「未初始化」调用
 * 按正常请求处理（协议允许，见 docs/contracts/mcp-v1.md）。
 */
import type { IncomingMessage, ServerResponse } from 'node:http';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import type { DatasetHolder } from './dataset.js';
import { TokenBucket } from './http.js';
import { registerMaasTools } from './mcp-tools.js';

export interface McpConfig {
  /** 存在 Origin 头时必须命中（缺省 Origin 的非浏览器客户端放行） */
  originAllowlist: string[];
  maxBodyBytes: number;
  rateLimit: { capacity: number; refillPerMinute: number };
}

export const DEFAULT_MCP_CONFIG: McpConfig = {
  originAllowlist: ['https://daily.maas.click'],
  maxBodyBytes: 256 * 1024,
  rateLimit: { capacity: 30, refillPerMinute: 30 },
};

export function createMcpHandler(holder: DatasetHolder, config: McpConfig) {
  const bucket = new TokenBucket(config.rateLimit.capacity, config.rateLimit.refillPerMinute);

  return async function handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
    // 所有 MCP 响应不进共享缓存（成功与错误）
    res.setHeader('Cache-Control', 'no-store');

    // 1. 方法白名单：合同锁定 POST /api/mcp（无 SSE 旧协议）
    if (req.method !== 'POST') {
      res.writeHead(405, { 'Content-Type': 'application/problem+json; charset=utf-8',
                           Allow: 'POST' })
        .end(JSON.stringify({
          type: 'https://daily.maas.click/problems/method-not-allowed',
          title: 'Method not allowed', status: 405,
          detail: `MCP 端点只接受 POST: ${req.method}`,
          code: 'method_not_allowed',
          recovery: '使用 POST 发送 JSON-RPC。',
        }));
      return;
    }

    // 2. 独立限流（429 + Retry-After；与 REST 匿名桶分离）
    if (!bucket.take()) {
      const retry = Math.max(bucket.retryAfterSeconds(), 1);
      res.writeHead(429, { 'Content-Type': 'application/problem+json; charset=utf-8',
                           'Retry-After': String(retry) })
        .end(JSON.stringify({
          type: 'https://daily.maas.click/problems/rate-limited',
          title: 'Too many requests', status: 429,
          detail: 'MCP 请求频率超限', code: 'rate_limited',
          recovery: `${retry} 秒后重试（见 Retry-After 头）。`,
        }));
      return;
    }

    // 3. Origin 校验：缺省放行（非浏览器客户端）；存在则必须命中白名单。
    //    拒绝发生在读 body 之前（T10：无副作用）。
    const origin = req.headers.origin;
    if (origin !== undefined && !config.originAllowlist.includes(origin)) {
      res.writeHead(403, { 'Content-Type': 'application/problem+json; charset=utf-8' })
        .end(JSON.stringify({
          type: 'https://daily.maas.click/problems/origin-forbidden',
          title: 'Origin forbidden', status: 403,
          detail: `Origin 不在白名单: ${origin}`,
          code: 'origin_forbidden',
          recovery: '浏览器客户端需在服务端配置允许的 Origin。',
        }));
      return;
    }

    // 4. 自读 body（实现 SDK 没有的大小上限）
    let body: unknown;
    try {
      body = await readBody(req, config.maxBodyBytes);
    } catch (e) {
      const err = e as { kind?: string; message?: string };
      if (err.kind === 'too_large') {
        req.destroy();
        res.writeHead(413, { 'Content-Type': 'application/problem+json; charset=utf-8' })
          .end(JSON.stringify({
            type: 'https://daily.maas.click/problems/request-too-large',
            title: 'Request too large', status: 413,
            detail: `MCP 请求体超过上限: ${config.maxBodyBytes} 字节`,
            code: 'request_too_large',
            recovery: '拆分请求（工具参数/cursor 长度限制见文档）。',
          }));
        return;
      }
      // 畸形 JSON（body 已读完但 parse 失败）→ 协议错误 -32700
      res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' })
        .end(JSON.stringify({
          jsonrpc: '2.0', id: null,
          error: { code: -32700, message: 'Parse error: 请求体不是合法 JSON' },
        }));
      return;
    }

    // 5. 每请求全新 McpServer + stateless transport（官方范式；
    //    工具闭包持有 holder，单次调用单 datasetVersion）
    const mcp = new McpServer({ name: 'maas-daily', version: '1.0.0' });
    registerMaasTools(mcp, holder);
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
    });
    res.on('close', () => {
      transport.close();
      mcp.close();
    });
    try {
      await mcp.connect(transport);
      // parsedBody：SDK 优先使用，不再自行读流（body limit 已在上层执行）
      await transport.handleRequest(req, res, body);
    } catch {
      // 兜底：不泄露堆栈或路径
      if (!res.headersSent) {
        res.writeHead(500, { 'Content-Type': 'application/problem+json; charset=utf-8' })
          .end(JSON.stringify({
            type: 'https://daily.maas.click/problems/internal-error',
            title: 'Internal error', status: 500,
            detail: '内部错误', code: 'internal_error',
            recovery: '请稍后重试。',
          }));
      } else {
        res.destroy();
      }
    } finally {
      // stateless：每请求关闭（res.on close 兜底，此处显式幂等）
      transport.close();
      mcp.close();
    }
  };
}

/** 读请求体并 JSON.parse；超限抛 {kind:'too_large'}，parse 失败抛原错误。 */
async function readBody(req: IncomingMessage, maxBytes: number): Promise<unknown> {
  const chunks: Buffer[] = [];
  let total = 0;
  for await (const chunk of req) {
    total += (chunk as Buffer).length;
    if (total > maxBytes) {
      const e = new Error('body too large') as Error & { kind?: string };
      e.kind = 'too_large';
      throw e;
    }
    chunks.push(chunk as Buffer);
  }
  const text = Buffer.concat(chunks).toString('utf-8');
  if (!text.trim()) {
    const e = new Error('empty body') as Error & { kind?: string };
    e.kind = 'empty';
    throw e;
  }
  return JSON.parse(text);
}
