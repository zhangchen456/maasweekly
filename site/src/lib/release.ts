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
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';

import { validateManifest, validateIdentityCatalog, validateCollections } from './public-contract/validation.ts';
import { readVerified } from './public-contract/node-reader.ts';
import type { Manifest, ChangeEntity, ItemEntity, PriceEntity, EvidenceEntity, WeeklyEntity, StatusEntity } from './public-contract/entities.ts';
export type ChangeRecord = ChangeEntity;
export type WeeklyRecord = WeeklyEntity;
export type PriceRecord = PriceEntity;
export type EvidenceRecord = EvidenceEntity;

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
  prices?: PriceRecord[];
  evidence?: EvidenceRecord[];
  /** T07-4A.2：model identity catalog（从 model-identities.json 经 manifest 校验加载） */
  modelIdentities?: { models: { modelId: string; modelName: string; familyId?: string; familyName?: string }[]; families: { familyId: string; familyName: string }[] };
}

const COLLECTION_FILE = {
  changes: 'changes.json',
  weekly: 'weekly.json',
  modelIdentities: 'model-identities.json',
  prices: 'prices.json',
  evidence: 'evidence.json',
} as const;

export function defaultPublicReleaseDir(): string {
  return path.join(process.cwd(), '..', 'data', 'public', 'v1');
}

/**
 * 读取并校验公开 release。
 * opts.select 控制加载哪些集合（agent/method 页只需 manifest；feed 全量）。
 * baseDir 参数供测试注入 fixture 目录（T16 / 复验 P1-1 反例）。
 */
export function loadVerifiedRelease(
  baseDir?: string,
  opts?: { select?: Array<keyof typeof COLLECTION_FILE> },
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
  const fullManifest = manifest as unknown as Manifest;
  validateManifest(fullManifest);
  const version = fullManifest.datasetVersion;
  const parsed: Record<string, unknown> = {};
  // The same complete hash/path/reference/order checks as the API, including unselected files.
  for (const entry of fullManifest.files) {
    parsed[path.basename(entry.path, '.json')] = JSON.parse(readVerified(path.resolve(root), entry));
  }
  validateIdentityCatalog(parsed['model-identities']);
  validateCollections(parsed.changes as ChangeEntity[], parsed.items as ItemEntity[], parsed.prices as PriceEntity[],
    parsed.evidence as EvidenceEntity[], parsed.weekly as WeeklyEntity[], parsed.status as StatusEntity);
  const out: PublicRelease = { datasetVersion: version, dataThrough: manifest.dataThrough, coverage: manifest.coverage };
  for (const key of opts?.select ?? []) {
    (out as Record<string, unknown>)[key] = parsed[COLLECTION_FILE[key].replace('.json', '')];
  }
  return out;
}
