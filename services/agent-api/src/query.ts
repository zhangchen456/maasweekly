/**
 * query.ts：公开数据查询（Task 03 M4）。无 node:http 依赖——供 MCP 复用。
 *
 * 覆盖任务书 §6.2/§6.3：参数规范化与校验（400 Problem）、时间窗口
 * （默认最近 7 上海日历日，锚定 release dataThrough 非墙钟）、
 * cursor（base64url 规范 JSON，绑定 datasetVersion/endpoint/查询摘要）、
 * keyset 分页（同版本全量翻页无重复无遗漏）。
 */
import { createHash, createHmac, timingSafeEqual } from 'node:crypto';
import type {
  ChangeEntity, Dataset, DatasetHolder, EvidenceEntity, ItemEntity,
  PriceEntity, WeeklyEntity,
} from './dataset.js';

export type Endpoint = 'changes' | 'prices' | 'weekly';

export interface Problem {
  type: string;
  title: string;
  status: 400 | 404 | 409 | 413 | 429 | 503;
  detail: string;
  code: string;
  recovery: string;
}

export interface NormalizedQuery {
  endpoint: Endpoint;
  params: Record<string, unknown>;
  qh: string;
}

export interface Page<T> {
  items: T[];
  limit: number;
  nextCursor: string | null;
}

export const DEFAULT_LIMIT = 20;
export const MAX_LIMIT = 100;

/** limit 策略：REST 与 MCP 共用 normalizeQuery，默认/上限不同（任务书 §4.2） */
export interface LimitPolicy { defaultLimit: number; maxLimit: number }
export const REST_LIMITS: LimitPolicy = { defaultLimit: DEFAULT_LIMIT, maxLimit: MAX_LIMIT };
export const MCP_LIMITS: LimitPolicy = { defaultLimit: 10, maxLimit: 30 };
export const MAX_WINDOW_DAYS = 90;
export const MAX_CURSOR_BYTES = 4096;

// ---------------------------------------------------------------------------
// 规范 JSON（与 Python canonical_json 同规则：sorted keys + 紧凑）
// ---------------------------------------------------------------------------

export function canonicalJson(value: unknown): string {
  const sort = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(sort);
    if (v && typeof v === 'object') {
      return Object.fromEntries(
        Object.entries(v as Record<string, unknown>)
          .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
          .map(([k, vv]) => [k, sort(vv)]),
      );
    }
    return v;
  };
  return JSON.stringify(sort(value));
}

function sha256(s: string): string {
  return createHash('sha256').update(s).digest('hex');
}

function timingSafeEqualStr(a: string, b: string): boolean {
  const ba = Buffer.from(a, 'utf-8');
  const bb = Buffer.from(b, 'utf-8');
  return ba.length === bb.length && timingSafeEqual(ba, bb);
}

// ---------------------------------------------------------------------------
// 参数解析与校验
// ---------------------------------------------------------------------------

const KNOWN_PARAMS: Record<Endpoint, Set<string>> = {
  changes: new Set(['provider', 'type', 'q', 'from', 'to', 'limit', 'cursor', 'includeWithdrawn', 'modelId', 'familyId']),
  prices: new Set(['provider', 'model', 'component', 'region', 'billingMode', 'q', 'limit', 'cursor', 'modelId', 'familyId']),
  weekly: new Set(['limit', 'cursor']),
};

const RECORD_TYPE_ALIAS: Record<string, string> = {
  source_observation: 'source_observation',
  source: 'source_observation',
  price_change: 'price_change',
  price: 'price_change',
};

export function normalizeQuery(
  endpoint: Endpoint,
  raw: URLSearchParams,
  ds: Dataset,
  limits: LimitPolicy = REST_LIMITS,
): { normalized?: NormalizedQuery; problems: Problem[] } {
  const problems: Problem[] = [];
  const bad = (code: string, detail: string, recovery: string): Problem => ({
    type: 'https://daily.maas.click/problems/invalid-query',
    title: 'Invalid query', status: 400, detail, code, recovery,
  });

  // 未知参数
  for (const key of new Set(raw.keys())) {
    if (!KNOWN_PARAMS[endpoint].has(key)) {
      problems.push(bad('unknown_parameter', `未知参数: ${key}`, `支持的参数: ${[...KNOWN_PARAMS[endpoint]].join(', ')}`));
    }
  }
  // 重复参数
  for (const key of new Set(raw.keys())) {
    if (raw.getAll(key).length > 1) {
      problems.push(bad('duplicate_parameter', `参数重复: ${key}`, '每个参数只传一次'));
    }
  }

  // cursor：唯一参数（与其他任何参数共存 → 400）。规范化照常进行
  //（空参数集 + 默认值），cursor 里的 qh 与之比对实现查询绑定。
  const cursorRaw = raw.get('cursor');
  if (cursorRaw !== null) {
    if ([...raw.keys()].some((k) => k !== 'cursor')) {
      problems.push(bad('cursor_conflict', 'cursor 不能与其他参数同时使用', 'cursor 单独传递，或去掉 cursor 从第一页查询'));
    }
  }

  const params: Record<string, unknown> = {};

  // limit（策略由调用方传入：REST 20/100，MCP 10/30——任务书 §4.2）
  const limitRaw = raw.get('limit');
  let limit = limits.defaultLimit;
  if (limitRaw !== null) {
    if (!/^\d+$/.test(limitRaw)) {
      problems.push(bad('invalid_limit', 'limit 必须是正整数', `1 到 ${limits.maxLimit} 的整数`));
    } else {
      limit = parseInt(limitRaw, 10);
      if (limit < 1 || limit > limits.maxLimit) {
        problems.push(bad('invalid_limit', `limit 超出范围: ${limit}`, `1 到 ${limits.maxLimit} 的整数`));
      }
    }
  }
  params.limit = limit;

  // q（2–100，Unicode trim + casefold）
  const qRaw = raw.get('q');
  if (qRaw !== null) {
    const q = qRaw.trim().toLocaleLowerCase('en-US');
    if (q.length < 2 || q.length > 100) {
      problems.push(bad('invalid_q', `q 长度非法: ${q.length}`, '2 到 100 个字符（trim 后）'));
    } else {
      params.q = q;
    }
  }

  // provider 枚举
  const provider = raw.get('provider');
  if (provider !== null) {
    if (!ds.enums.providers.has(provider)) {
      problems.push(bad('invalid_provider', `未知 provider: ${provider}`, `已收录平台: ${[...ds.enums.providers].join(', ')}`));
    } else {
      params.provider = provider;
    }
  }

  if (endpoint === 'changes') {
    // type
    const t = raw.get('type');
    if (t !== null) {
      const mapped = RECORD_TYPE_ALIAS[t];
      if (!mapped) {
        problems.push(bad('invalid_type', `未知 type: ${t}`, 'source_observation / price_change'));
      } else {
        params.type = mapped;
      }
    }
    // includeWithdrawn
    const iw = raw.get('includeWithdrawn');
    if (iw !== null) {
      if (iw !== 'true' && iw !== 'false') {
        problems.push(bad('invalid_flag', `includeWithdrawn 必须是 true/false: ${iw}`, 'true 或 false'));
      } else {
        params.includeWithdrawn = iw === 'true';
      }
    }
    // from/to
    const from = raw.get('from');
    const to = raw.get('to');
    const win = parseWindow(from, to, ds.dataThrough);
    if (win.problems) problems.push(...win.problems);
    else Object.assign(params, win.value);
  }

  if (endpoint === 'prices') {
    for (const [key, enumSet] of [
      ['component', ds.enums.components],
      ['billingMode', ds.enums.billingModes],
      ['region', ds.enums.regions],
    ] as const) {
      const v = raw.get(key);
      if (v !== null) {
        if (!enumSet.has(v)) {
          problems.push(bad(`invalid_${key}`, `未知 ${key}: ${v}`, `有效值: ${[...enumSet].join(', ')}`));
        } else {
          params[key] = v;
        }
      }
    }
    const model = raw.get('model');
    if (model !== null) {
      // 大小写不敏感精确匹配（规范化后），不维护别名推断
      // ——model 语义=modelKey 原始串（backward compat 红线：绝不改成 modelId 语义）
      params.model = model.trim().toLowerCase();
    }
  }

  // Task 07 T07-3：modelId / familyId 精确过滤（与 model 语义严格区分）
  // Task 07 T07-3：modelId/familyId 必须区分 格式非法 / registry 不存在 / 已存在无记录。
  // 不在 TS 手工枚举——用 ds.enums.validModelIds/validFamilyIds
  // （来源：registry public contract，见 dataset.enums）
  const modelId = raw.get('modelId');
  if (modelId !== null) {
    const v = modelId.trim();
    if (!/^[a-z0-9-]+:[a-z0-9.-]+$/.test(v)) {
      problems.push(bad('invalid_model_id', `modelId 格式非法: ${v}`,
        '完整精确 modelId，如 alibaba:qwen3-coder-plus'));
    } else if (!ds.enums.validModelIds.has(v)) {
      problems.push(bad('invalid_model_id', `未知 modelId: ${v}`,
        'registry 中不存在该 modelId'));
    } else {
      params.modelId = v;
    }
  }
  const familyId = raw.get('familyId');
  if (familyId !== null) {
    const v = familyId.trim();
    if (!/^[a-z0-9-]+:[a-z0-9.-]+$/.test(v)) {
      problems.push(bad('invalid_family_id', `familyId 格式非法: ${v}`,
        '完整正式 familyId，如 anthropic:claude-opus'));
    } else if (!ds.enums.validFamilyIds.has(v)) {
      problems.push(bad('invalid_family_id', `未知 familyId: ${v}`,
        'registry 中不存在该 familyId'));
    } else {
      params.familyId = v;
    }
  }

  if (problems.length > 0) return { problems };

  const qh = sha256(canonicalJson({ endpoint, params })).slice(0, 16);
  return { normalized: { endpoint, params, qh }, problems: [] };
}

// ---------------------------------------------------------------------------
// 时间窗口
// ---------------------------------------------------------------------------

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function shanghaiDateOffset(base: string, days: number): string {
  const d = new Date(`${base}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function parseWindow(
  from: string | null, to: string | null, dataThrough: string,
): { value?: Record<string, string>; problems?: Problem[] } {
  const bad = (code: string, detail: string, recovery: string): Problem => ({
    type: 'https://daily.maas.click/problems/invalid-query',
    title: 'Invalid query', status: 400, detail, code, recovery,
  });
  if (from === null && to === null) {
    // 默认：dataThrough 锚定最近 7 上海日历日，统一 [from, to) 语义
    //（to = D+1 使窗口含当日 D，共 7 天）
    if (!DATE_RE.test(dataThrough)) return { problems: [bad('no_anchor', 'release 缺 dataThrough', '稍后重试')] };
    return { value: { from: shanghaiDateOffset(dataThrough, -6), to: shanghaiDateOffset(dataThrough, 1) } };
  }
  if ((from !== null) !== (to !== null)) {
    return { problems: [bad('partial_window', 'from 与 to 必须同时提供', '同时提供 YYYY-MM-DD 的 from 与 to')] };
  }
  if (!DATE_RE.test(from!) || !DATE_RE.test(to!)) {
    return { problems: [bad('invalid_date', '日期格式非法（仅支持 YYYY-MM-DD）', '如 2026-09-01')] };
  }
  if (from! >= to!) {
    return { problems: [bad('invalid_window', `from 必须早于 to: ${from} >= ${to}`, 'from < to，窗口为 [from, to)')] };
  }
  const days = (Date.parse(to!) - Date.parse(from!)) / 86400000;
  if (days > MAX_WINDOW_DAYS) {
    return { problems: [bad('window_too_large', `窗口超上限: ${days} 天`, `最多 ${MAX_WINDOW_DAYS} 天`)] };
  }
  return { value: { from: from!, to: to! } };
}

// ---------------------------------------------------------------------------
// cursor
// ---------------------------------------------------------------------------

export interface CursorPayload {
  v: number;
  sv: string;
  ds: string;
  ep: Endpoint;
  qh: string;
  /** 原始规范化查询参数（cursor 翻页时服务端恢复查询，不要求客户端重传） */
  qp: Record<string, unknown>;
  k: (string | number)[];
  /** HMAC-SHA256 签名（验收 P1-2：无密钥哈希可被调用方重算伪造，
   * qp 里的 limit/窗口/枚举可被篡改绕过校验。MAC 密钥服务端持有，
   * 改任何字段后签名不符 → 400，且恢复查询时仍重新执行全量校验。） */
  mac?: string;
}

function b64urlEncode(s: string): string {
  return Buffer.from(s, 'utf-8').toString('base64url');
}

/** 进程级 MAC 密钥：单实例内自洽；多实例部署需共享 CURSOR_SECRET。 */
let cursorSecret: Buffer | null = null;

export function setCursorSecret(secret: string): void {
  cursorSecret = Buffer.from(secret, 'utf-8');
}

function cursorMac(payload: Omit<CursorPayload, 'mac'>): string {
  const secret = cursorSecret ?? Buffer.alloc(0);
  return createHmac('sha256', secret)
    .update(canonicalJson(payload))
    .digest('base64url');
}

export function encodeCursor(p: CursorPayload): string {
  const { mac: _omit, ...body } = p;
  return b64urlEncode(canonicalJson({ ...body, mac: cursorMac(body) }));
}

export function decodeCursor(
  raw: string, endpoint: Endpoint, schemaVersion: string,
): { payload?: CursorPayload; problem?: Problem } {
  const bad = (code: string, detail: string, recovery: string): Problem => ({
    type: 'https://daily.maas.click/problems/invalid-cursor',
    title: 'Invalid cursor', status: 400, detail, code, recovery,
  });
  if (raw.length > MAX_CURSOR_BYTES) {
    return { problem: {
      type: 'https://daily.maas.click/problems/request-too-large',
      title: 'Request too large', status: 413,
      detail: `cursor 超长: ${raw.length}`,
      code: 'request_too_large',
      recovery: '从第一页重新查询',
    } };
  }
  let p: CursorPayload;
  try {
    p = JSON.parse(Buffer.from(raw, 'base64url').toString('utf-8')) as CursorPayload;
  } catch {
    return { problem: bad('invalid_cursor', 'cursor 解码失败', '从第一页重新查询') };
  }
  if (p.v !== 1 || p.sv !== schemaVersion) {
    return { problem: bad('cursor_version', 'cursor 版本不匹配', '从第一页重新查询') };
  }
  if (p.ep !== endpoint) {
    return { problem: bad('cursor_endpoint', `cursor 属于 ${p.ep} 端点`, `在 ${p.ep} 端点使用该 cursor`) };
  }
  if (typeof p.qh !== 'string' || p.qh.length !== 16) {
    return { problem: bad('invalid_cursor', 'cursor 查询摘要非法', '从第一页重新查询') };
  }
  if (!p.qp || typeof p.qp !== 'object' || Array.isArray(p.qp)) {
    return { problem: bad('invalid_cursor', 'cursor 缺查询参数', '从第一页重新查询') };
  }
  // MAC 签名（P1-2：结构自洽 + 签名双保险——即使知道 qh 算法，
  // 无密钥也伪造不出有效 cursor）
  if (typeof p.mac !== 'string') {
    return { problem: bad('invalid_cursor', 'cursor 缺签名', '从第一页重新查询') };
  }
  const { mac, ...body } = p;
  const expected = cursorMac(body);
  if (mac.length !== expected.length
      || !timingSafeEqualStr(mac, expected)) {
    return { problem: bad('invalid_cursor', 'cursor 签名不符（篡改拒绝）', '从第一页重新查询') };
  }
  // qh 与 qp 自洽（层级校验：MAC 通过后仍验，防御密钥泄露场景）
  const recomputed = sha256(canonicalJson({ endpoint, params: p.qp })).slice(0, 16);
  if (recomputed !== p.qh) {
    return { problem: bad('cursor_query_mismatch', 'cursor 查询摘要与参数不一致', '从第一页重新查询') };
  }
  if (!Array.isArray(p.k) || p.k.length === 0) {
    return { problem: bad('invalid_cursor', 'cursor 缺排序键', '从第一页重新查询') };
  }
  return { payload: p };
}

// ---------------------------------------------------------------------------
// 查询执行（keyset 分页）
// ---------------------------------------------------------------------------

function cmpSortKey(a: (string | number)[], b: (string | number)[]): number {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    const av = a[i]!, bv = b[i]!;
    if (av < bv) return -1;
    if (av > bv) return 1;
  }
  return 0;
}

export function listChanges(ds: Dataset, nq: NormalizedQuery, cursor?: CursorPayload): Page<ChangeEntity> {
  const p = nq.params;
  const includeWithdrawn = p.includeWithdrawn === true;
  const from = p.from as string;
  const to = p.to as string; // 窗口 [from, to)（to 为默认窗口末日的次日语义见合同；实现上 to 为闭端）
  let out = ds.changes.filter((c) => {
    if (!includeWithdrawn && c.status === 'withdrawn') return false;
    // 窗口 [from, to)：to 当日不含（任务书 §6.2 绝对窗口语义）
    if (c.observationDate < from || c.observationDate >= to) return false;
    if (p.provider !== undefined && c.providerId !== p.provider) return false;
    if (p.type !== undefined && c.recordType !== p.type) return false;
    // Task 07 T07-3：modelId/familyId 精确过滤（identity 在 price_change.price；
    // source_observation 无结构化模型——自然过滤，不伪造）
    if (p.modelId !== undefined) {
      const pc = c as unknown as { price?: { modelId?: string } };
      if (pc.price?.modelId !== p.modelId) return false;
    }
    if (p.familyId !== undefined) {
      const pc = c as unknown as { price?: { familyId?: string } };
      if (pc.price?.familyId !== p.familyId) return false;
    }
    if (p.q !== undefined) {
      const q = p.q as string;
      const hay = `${c.title} ${c.summary ?? ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  // 排序键：[日期取反序 → 用倒序比较]，实现：日期 desc、id asc
  // keyset：cursor.k = [date, id]；定位 = 日期 < k.date || (== 且 id > k.id)
  if (cursor) {
    const [kd, ki] = cursor.k as [string, string];
    out = out.filter((c) => c.observationDate < kd || (c.observationDate === kd && c.id > ki));
  }
  const limit = p.limit as number;
  const page = out.slice(0, limit);
  const last = page.at(-1);
  const nextCursor = out.length > limit && last
    ? encodeCursor({ v: 1, sv: '1.0', ds: ds.version, ep: 'changes', qh: nq.qh,
                     qp: nq.params, k: [last.observationDate, last.id] })
    : null;
  return { items: page, limit, nextCursor };
}

export function listPrices(ds: Dataset, nq: NormalizedQuery, cursor?: CursorPayload): Page<PriceEntity> {
  const p = nq.params;
  let out = ds.prices.filter((e) => {
    if (p.provider !== undefined && e.providerId !== p.provider) return false;
    if (p.model !== undefined && e.modelKey.toLowerCase() !== p.model) return false;
    if (p.modelId !== undefined && e.modelId !== p.modelId) return false;
    if (p.familyId !== undefined && e.familyId !== p.familyId) return false;
    if (p.component !== undefined && e.component !== p.component) return false;
    if (p.region !== undefined && e.region !== p.region) return false;
    if (p.billingMode !== undefined && e.billingMode !== p.billingMode) return false;
    if (p.q !== undefined) {
      const q = p.q as string;
      if (!e.modelKey.toLowerCase().includes(q)) return false;
    }
    return true;
  });
  if (cursor) {
    const key = cursor.k.map(String);
    out = out.filter((e) =>
      cmpSortKey([e.providerId, e.modelKey, e.component, e.factKey], key) > 0);
  }
  const limit = p.limit as number;
  const page = out.slice(0, limit);
  const last = page.at(-1);
  const nextCursor = out.length > limit && last
    ? encodeCursor({ v: 1, sv: '1.0', ds: ds.version, ep: 'prices', qh: nq.qh,
                     qp: nq.params, k: [last.providerId, last.modelKey, last.component, last.factKey] })
    : null;
  return { items: page, limit, nextCursor };
}

export function listWeekly(ds: Dataset, nq: NormalizedQuery, cursor?: CursorPayload): Page<WeeklyEntity> {
  // 最新在前
  const sorted = [...ds.weekly].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  let out = sorted;
  if (cursor) {
    const [kd] = cursor.k as [string];
    out = out.filter((w) => w.date < kd);
  }
  const limit = nq.params.limit as number;
  const page = out.slice(0, limit);
  const last = page.at(-1);
  const nextCursor = out.length > limit && last
    ? encodeCursor({ v: 1, sv: '1.0', ds: ds.version, ep: 'weekly', qh: nq.qh,
                     qp: nq.params, k: [last.date] })
    : null;
  return { items: page, limit, nextCursor };
}

export function getItem(ds: Dataset, id: string): ItemEntity | null {
  return ds.itemsById.get(id) ?? null;
}

export function getEvidence(ds: Dataset, id: string): EvidenceEntity | null {
  return ds.evidenceById.get(id) ?? null;
}

export function getWeekly(ds: Dataset, id: string): WeeklyEntity | null {
  return ds.weekly.find((w) => w.id === id) ?? null;
}

// ---------------------------------------------------------------------------
// runListQuery：列表查询统一入口（REST 与 MCP 共用，Task 04 D2）
// ---------------------------------------------------------------------------

export interface ListResult {
  /** 实际执行的 dataset（第一页=current；翻页=cursor 固定版本） */
  ds: Dataset;
  /** 实际执行的规范化查询（翻页时来自 cursor 恢复） */
  nq: NormalizedQuery;
  page: Page<ChangeEntity> | Page<PriceEntity> | Page<WeeklyEntity>;
}

/** 列表查询全流程：normalizeQuery → cursor 解码/版本固定/恢复重验 → list。
 *
 * 语义与原 http.ts handleList 逐行对应（Task 03 复验 P1-2 的双层防御
 * 全部保留）；REST 与 MCP 调用同一实现，保证实体/顺序/coverage/版本
 * 完全一致。problem 由调用方映射到各自传输层（REST: Problem JSON；
 * MCP: isError 工具错误）。
 */
export function runListQuery(
  holder: DatasetHolder, endpoint: Endpoint, raw: URLSearchParams,
  limits: LimitPolicy = REST_LIMITS,
): { result?: ListResult; problem?: Problem } {
  const current = holder.current;
  if (!current) {
    return { problem: {
      type: 'https://daily.maas.click/problems/no-data',
      title: 'Service unavailable', status: 503,
      detail: '当前无有效数据版本', code: 'no_data_available',
      recovery: '稍后重试；数据发布后自动恢复。',
    } };
  }
  const { normalized, problems } = normalizeQuery(endpoint, raw, current, limits);
  if (problems.length > 0) return { problem: problems[0]! };
  const nq = normalized!;

  let cursor: CursorPayload | undefined;
  let activeDs = current;
  let query = nq;
  const cursorRaw = raw.get('cursor');
  if (cursorRaw !== null) {
    const dec = decodeCursor(cursorRaw, endpoint, '1.0');
    if (dec.problem) return { problem: dec.problem };
    const payload = dec.payload!;
    const versioned = holder.getOrLoad(payload.ds);
    if (!versioned) {
      return { problem: {
        type: 'https://daily.maas.click/problems/dataset-version-expired',
        title: 'Dataset version expired', status: 409,
        detail: `cursor 指向的版本已清理: ${payload.ds}`,
        code: 'dataset_version_expired',
        recovery: '去掉 cursor 从第一页重新查询（数据已更新）。',
      } };
    }
    // 恢复查询重新全量校验（qp 来自 cursor；对 versioned 的枚举同样重验）
    const qpEntries = Object.entries(payload.qp)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, String(v)] as [string, string]);
    const recheck = normalizeQuery(
      endpoint, new URLSearchParams(qpEntries), versioned, limits);
    if (recheck.problems.length > 0) return { problem: recheck.problems[0]! };
    if (canonicalJson(recheck.normalized!.params) !== canonicalJson(payload.qp)) {
      return { problem: {
        type: 'https://daily.maas.click/problems/invalid-cursor',
        title: 'Invalid cursor', status: 400,
        detail: 'cursor 查询参数无法通过规范化',
        code: 'invalid_cursor',
        recovery: '从第一页重新查询。',
      } };
    }
    activeDs = versioned;
    query = { endpoint, params: payload.qp, qh: payload.qh };
    cursor = payload;
  }
  const page = endpoint === 'changes' ? listChanges(activeDs, query, cursor)
    : endpoint === 'prices' ? listPrices(activeDs, query, cursor)
    : listWeekly(activeDs, query, cursor);
  return { result: { ds: activeDs, nq: query, page } };
}
