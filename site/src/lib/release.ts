/**
 * release.ts：公开 release 读取 + 完整性校验（Task 05 M2；复验 P1-1 强化）。
 *
 * site 构建 cwd 是 site/，仓库级数据用 process.cwd(),'..','data'。
 * 硬错误惯例对齐 evidence/[id].astro：任何校验失败 → throw（构建中止），
 * 绝不产出空 feed 或加载未签名内容。
 *
 * 复验 P1-1 修复的校验链（缺一不可，全部通过后才解析 JSON）：
 * 1. manifest 存在且可解析；datasetVersion 格式 ds_<64hex>；
 * 2. select 请求的每个文件必须在 manifest.files 中**恰好出现一次**
 *    （清单为空/文件被删除 → 拒绝，防 TAMPERED 内容绕过）；
 * 3. manifest.files 条目路径必须在 releases/{datasetVersion}/ 下
 *    （拒绝对路径/../逃逸/其他版本目录——防版本错位与目录穿越）；
 * 4. 文件存在 + bytes + SHA-256 与清单一致后才能 JSON.parse。
 * 错误信息只含相对路径与规则名，不泄露本机绝对路径或恶意原文。
 */
import { createHash } from 'node:crypto';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';

export interface ChangeRecord {
  id: string;
  revision: number;
  status: 'active' | 'withdrawn';
  recordType: 'source_observation' | 'price_change';
  providerId: string | null;
  observedAt: string | null;
  observationDate: string;
  timePrecision: 'date' | 'datetime';
  title: string;
  summary: string | null;
  summaryOrigin: 'rule' | 'llm' | 'manual' | null;
  changeType: string;
  price?: {
    model: string; component: string; currency: string;
    beforeAmount: string | null; afterAmount: string | null;
    unitQuantity: number; unitName: string;
  } | null;
  links: { permalink: string };
}

export interface WeeklyRecord {
  id: string;
  title: string;
  date: string;
  period: string | null;
  url: string;
  headline: unknown[];
}

export interface ReleaseManifest {
  schemaVersion: string;
  datasetVersion: string;
  dataThrough: string;
  coverage: {
    changes: { from: string; to: string; count: number };
    prices: { facts: number };
    evidence: { count: number };
    weekly: { count: number; latestId: string };
  };
  files: { path: string; sha256: string; bytes: number }[];
}

export interface PublicRelease {
  datasetVersion: string;
  dataThrough: string;
  coverage: ReleaseManifest['coverage'];
  changes?: ChangeRecord[];
  weekly?: WeeklyRecord[];
}

const DS_VERSION_RE = /^ds_[0-9a-f]{64}$/;
const COLLECTION_FILE: Record<'changes' | 'weekly', string> = {
  changes: 'changes.json',
  weekly: 'weekly.json',
};

export function defaultPublicReleaseDir(): string {
  return path.join(process.cwd(), '..', 'data', 'public', 'v1');
}

/** manifest 条目路径合法性：必须在 releases/{version}/ 下且无逃逸。 */
function assertManifestPath(entryPath: string, version: string): void {
  const prefix = `releases/${version}/`;
  if (!entryPath.startsWith(prefix) || entryPath.length <= prefix.length) {
    throw new Error(
      `[release] manifest 文件路径越界（构建中止）: 期望前缀 ${prefix}`);
  }
  const rel = entryPath.slice(prefix.length);
  if (path.isAbsolute(rel) || rel.split('/').includes('..') || rel.startsWith('/')) {
    throw new Error('[release] manifest 文件路径含目录逃逸（构建中止）');
  }
}

/**
 * 读取并校验公开 release。
 * opts.select 控制加载哪些集合（agent/method 页只需 manifest；feed 全量）。
 * baseDir 参数供测试注入 fixture 目录（T16 / 复验 P1-1 反例）。
 */
export function loadVerifiedRelease(
  baseDir?: string,
  opts?: { select?: Array<'changes' | 'weekly'> },
): PublicRelease {
  const root = baseDir ?? defaultPublicReleaseDir();
  const manifestPath = path.join(root, 'manifest.json');
  if (!existsSync(manifestPath)) {
    throw new Error('[release] 公开数据 manifest 不存在（构建中止）');
  }
  let manifest: ReleaseManifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
  } catch (e) {
    throw new Error(`[release] manifest 损坏（构建中止）: ${(e as Error).message}`);
  }
  const version = manifest.datasetVersion;
  if (typeof version !== 'string' || !DS_VERSION_RE.test(version)) {
    throw new Error('[release] manifest datasetVersion 格式非法（构建中止）');
  }

  // 全部清单条目先做路径合法性检查（含未 select 的——清单本身要干净）
  for (const f of manifest.files ?? []) {
    if (typeof f.path !== 'string' || typeof f.sha256 !== 'string'
        || typeof f.bytes !== 'number') {
      throw new Error('[release] manifest files 条目字段非法（构建中止）');
    }
    assertManifestPath(f.path, version);
  }

  // select 的文件必须在清单中恰好出现一次（复验 P1-1：防清单删除后
  // 直接读目录里的未签名文件）
  const select = opts?.select ?? [];
  const fileList = manifest.files ?? [];
  const seen = new Set<string>();
  for (const f of fileList) {
    if (seen.has(f.path)) {
      throw new Error(`[release] manifest 文件路径重复（构建中止）: ${f.path}`);
    }
    seen.add(f.path);
  }
  for (const key of select) {
    const want = `releases/${version}/${COLLECTION_FILE[key]}`;
    const hits = fileList.filter((f) => f.path === want);
    if (hits.length === 0) {
      throw new Error(
        `[release] 请求加载的文件不在 manifest 清单（构建中止）: ${COLLECTION_FILE[key]}`);
    }
    if (hits.length > 1) {
      throw new Error(
        `[release] manifest 清单条目重复（构建中止）: ${COLLECTION_FILE[key]}`);
    }
  }

  // 逐文件校验函数：bytes + sha256 全通过才返回内容
  const verifyAndRead = (rel: string): string => {
    const entry = fileList.find((f) => f.path === rel)!;
    const p = path.join(root, rel);
    if (!existsSync(p)) {
      throw new Error(`[release] manifest 文件缺失（构建中止）: ${rel}`);
    }
    const data = readFileSync(p);
    if (data.length !== entry.bytes) {
      throw new Error(`[release] 文件 bytes 不符（构建中止）: ${rel}`);
    }
    const sha = createHash('sha256').update(data).digest('hex');
    if (sha !== entry.sha256) {
      throw new Error(`[release] 文件 sha256 不符（构建中止）: ${rel}`);
    }
    return data.toString('utf-8');
  };

  const out: PublicRelease = {
    datasetVersion: version,
    dataThrough: manifest.dataThrough,
    coverage: manifest.coverage,
  };
  // 校验全通过后才解析（绝不解析未校验内容）
  for (const key of select) {
    const rel = `releases/${version}/${COLLECTION_FILE[key]}`;
    let parsed: unknown;
    try {
      parsed = JSON.parse(verifyAndRead(rel));
    } catch (e) {
      if (e instanceof Error && e.message.startsWith('[release]')) throw e;
      throw new Error(`[release] release 文件损坏（构建中止）: ${COLLECTION_FILE[key]}`);
    }
    (out as Record<string, unknown>)[key] = parsed;
  }
  return out;
}
