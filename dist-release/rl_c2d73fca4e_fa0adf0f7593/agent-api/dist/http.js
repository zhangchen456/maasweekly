import { createHash, randomUUID } from 'node:crypto';
import { getItem, getEvidence, getWeekly, runListQuery, } from './query.js';
import { PUBLIC_BASE_URL } from './public-consts.js';
const BASE_URL = PUBLIC_BASE_URL;
const SCHEMA_VERSION = '1.0';
const MAX_URL = 8 * 1024;
/** 路由元数据（OpenAPI 对照测试 import 此表，T17）。 */
export const ROUTES = [
    { method: 'GET', path: '/api/v1/changes',
        params: ['provider', 'type', 'q', 'from', 'to', 'limit', 'cursor', 'includeWithdrawn'],
        statusCodes: [200, 304, 400, 409, 413, 429, 503] },
    { method: 'GET', path: '/api/v1/items/{id}', params: [],
        statusCodes: [200, 304, 404, 429, 503] },
    { method: 'GET', path: '/api/v1/prices',
        params: ['provider', 'model', 'component', 'region', 'billingMode', 'q', 'limit', 'cursor'],
        statusCodes: [200, 304, 400, 409, 413, 429, 503] },
    { method: 'GET', path: '/api/v1/evidence/{id}', params: [],
        statusCodes: [200, 304, 404, 429, 503] },
    { method: 'GET', path: '/api/v1/weekly',
        params: ['limit', 'cursor'], statusCodes: [200, 304, 400, 409, 413, 429, 503] },
    { method: 'GET', path: '/api/v1/weekly/{id}', params: [],
        statusCodes: [200, 304, 404, 429, 503] },
    { method: 'GET', path: '/api/v1/status', params: [],
        statusCodes: [200, 304, 429, 503] },
];
// ---------------------------------------------------------------------------
// 限流（进程内令牌桶，匿名共享；Task 06 再决定 nginx 层）
// ---------------------------------------------------------------------------
export class TokenBucket {
    capacity;
    refillPerMin;
    #tokens;
    #last = Date.now();
    constructor(capacity, refillPerMin) {
        this.capacity = capacity;
        this.refillPerMin = refillPerMin;
        this.#tokens = capacity;
    }
    take() {
        const now = Date.now();
        this.#tokens = Math.min(this.capacity, this.#tokens + ((now - this.#last) / 60000) * this.refillPerMin);
        this.#last = now;
        if (this.#tokens >= 1) {
            this.#tokens -= 1;
            return true;
        }
        return false;
    }
    retryAfterSeconds() {
        return Math.ceil((1 - this.#tokens) / (this.refillPerMin / 60));
    }
}
// ---------------------------------------------------------------------------
// Problem JSON
// ---------------------------------------------------------------------------
function problem(res, requestId, p, extra) {
    const body = JSON.stringify({
        type: `${BASE_URL}/problems/${p.code.replace(/_/g, '-')}`,
        title: p.title,
        status: p.status,
        detail: p.detail,
        code: p.code,
        requestId,
        ...(p.recovery ? { recovery: p.recovery } : {}),
    });
    res.writeHead(p.status, {
        'Content-Type': 'application/problem+json; charset=utf-8',
        'Cache-Control': 'no-store',
        'X-Request-Id': requestId,
        ...extra,
    });
    res.end(body);
}
function notFound(res, requestId, detail) {
    problem(res, requestId, {
        type: '', title: 'Not found', status: 404, detail, code: 'not_found',
        recovery: '检查路径与 ID；可用端点见 /api/v1/status 与 OpenAPI 文档。',
    });
}
function serviceUnavailable(res, requestId, reason) {
    problem(res, requestId, {
        type: '', title: 'Service unavailable', status: 503,
        detail: `无有效数据版本可用: ${reason}`, code: 'no_data_available',
        recovery: '稍后重试；数据发布后自动恢复。',
    });
}
// ---------------------------------------------------------------------------
// 响应（ETag/304 + 公共元数据）
// ---------------------------------------------------------------------------
function sendJson(req, res, requestId, status, payload) {
    const body = JSON.stringify(payload);
    const etag = `"${createHash('sha256').update(body).digest('hex').slice(0, 32)}"`;
    const headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'max-age=0, s-maxage=300',
        'X-Request-Id': requestId,
        ETag: etag,
        Vary: 'Accept-Encoding',
    };
    const inm = req.headers['if-none-match'];
    if (inm === etag || inm === '*') {
        res.writeHead(304, headers);
        res.end();
        return;
    }
    if (req.method === 'HEAD') {
        headers['Content-Length'] = Buffer.byteLength(body);
        res.writeHead(status, headers);
        res.end();
        return;
    }
    res.writeHead(status, headers);
    res.end(body);
}
function envelope(ds, query, coverage) {
    return {
        schemaVersion: SCHEMA_VERSION,
        datasetVersion: ds.version,
        dataThrough: ds.dataThrough || ds.changes[0]?.observationDate || '',
        query,
        coverage,
    };
}
// ---------------------------------------------------------------------------
// 请求分发
// ---------------------------------------------------------------------------
export function createHandler(holder, config) {
    const bucket = new TokenBucket(config.rateLimit.capacity, config.rateLimit.refillPerMinute);
    return async function handle(req, res) {
        const requestId = randomUUID();
        // CORS（匿名，无 credentials）
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'If-None-Match');
        res.setHeader('Access-Control-Expose-Headers', 'ETag, Retry-After, X-Request-Id');
        if (req.method === 'OPTIONS') {
            res.writeHead(204, { 'Access-Control-Max-Age': '86400' });
            res.end();
            return;
        }
        if (req.method !== 'GET' && req.method !== 'HEAD') {
            problem(res, requestId, {
                type: '', title: 'Method not allowed', status: 404,
                detail: `不支持的方法: ${req.method}`, code: 'method_not_allowed',
                recovery: '只读服务：GET / HEAD / OPTIONS。',
            });
            return;
        }
        if (!req.url || req.url.length > MAX_URL) {
            problem(res, requestId, {
                type: '', title: 'Request too large', status: 413,
                detail: 'URL 超长', code: 'request_too_large',
                recovery: '缩短查询（q/cursor 长度限制见文档）。',
            });
            return;
        }
        // 限流（OPTIONS 外的所有请求）
        if (!bucket.take()) {
            const retry = bucket.retryAfterSeconds();
            res.setHeader('Retry-After', String(Math.max(retry, 1)));
            problem(res, requestId, {
                type: '', title: 'Too many requests', status: 429,
                detail: '请求频率超限', code: 'rate_limited',
                recovery: `${Math.max(retry, 1)} 秒后重试（见 Retry-After 头）。`,
            }, { 'Retry-After': String(Math.max(retry, 1)) });
            return;
        }
        let url;
        try {
            url = new URL(req.url, BASE_URL);
        }
        catch {
            notFound(res, requestId, 'URL 解析失败');
            return;
        }
        // 路径解码后再校验（不允许 ..、空字节、多斜杠穿越）
        let pathname;
        try {
            pathname = decodeURIComponent(url.pathname);
        }
        catch {
            notFound(res, requestId, '路径编码非法');
            return;
        }
        if (pathname.includes('..') || pathname.includes('\0') || /\/{2,}/.test(pathname)) {
            notFound(res, requestId, '路径非法');
            return;
        }
        const ds = holder.current;
        const seg = pathname.split('/').filter(Boolean); // ['api','v1',...]
        // 路由匹配（不做通配/文件读取）
        if (seg[0] === 'api' && seg[1] === 'v1') {
            const rest = seg.slice(2);
            try {
                if (rest.length === 0) {
                    notFound(res, requestId, '根路径无内容；可用端点: /api/v1/changes /prices /items/{id} /evidence/{id} /weekly /weekly/{id} /status');
                    return;
                }
                if (!ds && rest[0] !== 'status') {
                    serviceUnavailable(res, requestId, holder.lastReloadError ?? '启动中');
                    return;
                }
                switch (rest[0]) {
                    case 'changes':
                        return handleList(req, res, requestId, ds, 'changes', url, holder);
                    case 'prices':
                        return handleList(req, res, requestId, ds, 'prices', url, holder);
                    case 'weekly':
                        if (rest.length === 1) {
                            return handleList(req, res, requestId, ds, 'weekly', url, holder);
                        }
                        if (rest.length === 2) {
                            const w = getWeekly(ds, rest[1]);
                            if (!w) {
                                notFound(res, requestId, `未知周报: ${rest[1]}`);
                                return;
                            }
                            return sendJson(req, res, requestId, 200, {
                                ...envelope(ds, { id: w.id }, ds.coverage),
                                item: w,
                            });
                        }
                        notFound(res, requestId, '路径过深');
                        return;
                    case 'items':
                    case 'evidence': {
                        if (rest.length !== 2) {
                            notFound(res, requestId, '需要 ID');
                            return;
                        }
                        const id = rest[1];
                        const entity = rest[0] === 'items' ? getItem(ds, id) : getEvidence(ds, id);
                        if (!entity) {
                            notFound(res, requestId, `未知 ${rest[0] === 'items' ? '条目' : '证据'}: ${id}`);
                            return;
                        }
                        return sendJson(req, res, requestId, 200, {
                            ...envelope(ds, { id }, ds.coverage),
                            item: entity,
                        });
                    }
                    case 'status': {
                        const payload = ds
                            ? {
                                ...envelope(ds, {}, ds.coverage),
                                status: { ...ds.status, service: {
                                        lastReloadAt: holder.lastReloadAt,
                                        lastReloadError: holder.lastReloadError,
                                    } },
                            }
                            : {
                                schemaVersion: SCHEMA_VERSION,
                                datasetVersion: null,
                                dataThrough: null,
                                query: {},
                                coverage: {},
                                status: { providers: [], sourceStreams: [], priceStreams: [],
                                    weekly: { count: 0, latestId: null }, counts: {},
                                    service: {
                                        lastReloadAt: holder.lastReloadAt,
                                        lastReloadError: holder.lastReloadError ?? '无有效数据版本',
                                    } },
                            };
                        return sendJson(req, res, requestId, 200, payload);
                    }
                    default:
                        notFound(res, requestId, `未知端点: /${rest.join('/')}`);
                        return;
                }
            }
            catch (e) {
                problem(res, requestId, {
                    type: '', title: 'Internal error', status: 503,
                    detail: e.message, code: 'internal_error',
                    recovery: '稍后重试。',
                });
                return;
            }
        }
        notFound(res, requestId, `路径不在 /api/v1 下: ${pathname}`);
    };
}
function handleList(req, res, requestId, ds, endpoint, url, holder) {
    // 统一列表查询入口（Task 04 D2：与 MCP 共用 runListQuery——
    // normalizeQuery → cursor 解码/版本固定/恢复重验 → list 全流程单点）
    const { result, problem: p } = runListQuery(holder, endpoint, url.searchParams);
    if (p) {
        problem(res, requestId, p);
        return;
    }
    const { ds: activeDs, nq: query, page } = result;
    sendJson(req, res, requestId, 200, {
        ...envelope(activeDs, query.params, activeDs.coverage),
        items: page.items,
        page: { limit: page.limit, nextCursor: page.nextCursor },
    });
}
