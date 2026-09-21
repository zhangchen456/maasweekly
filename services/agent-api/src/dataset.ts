/**
 * dataset.ts：公开数据 release 的加载、校验与原子重载（Task 03 M4）。
 *
 * Dataset.load：manifest → 路径安全校验 → 逐文件 hash/bytes 比对 →
 * 结构 spot-check → 内存索引。任一步失败抛 DatasetError（不产出半成品）。
 *
 * DatasetHolder：current + retained（cursor 固定版本用）。重载 = 先完整
 * 加载新 release，成功后单一赋值替换；失败继续服务旧版并记录错误。
 * 单次请求只持有一个 Dataset 实例——重载是引用替换，不会混版。
 */
import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
import path from 'node:path';

export const SCHEMA_VERSION = '1.0';

export interface ManifestFileEntry {
  path: string;
  sha256: string;
  bytes: number;
}
export interface Manifest {
  schemaVersion: string;
  datasetVersion: string;
  generatedAt: string;
  dataThrough: string;
  coverage: Record<string, unknown>;
  files: ManifestFileEntry[];
  retainedVersions: { datasetVersion: string; generatedAt: string }[];
}

export interface ChangeEntity {
  id: string;
  revision: number;
  status: 'active' | 'withdrawn';
  recordType: 'source_observation' | 'price_change';
  providerId: string | null;
  sourceId: string;
  sourceType?: string | null;
  observedAt: string | null;
  observationDate: string;
  timePrecision: 'date' | 'datetime';
  publishedAt: string | null;
  updatedAt: string | null;
  title: string;
  summary: string | null;
  summaryOrigin: 'rule' | 'llm' | 'manual' | null;
  changeType: string;
  evidenceLevel: string;
  quality: { state: string; reason: string | null; lastSuccessAt: string | null };
  diff?: {
    addedLines: string[]; removedLines: string[];
    addedCount: number; removedCount: number; completeness: string | null;
  };
  price?: {
    factKey: string; model: string; component: string; currency: string;
    unitQuantity: number; unitName: string; region: string; billingMode: string;
    serviceTier: string; contextBand: Record<string, unknown> | null;
    timeCondition: Record<string, unknown> | null;
    beforeAmount: string | null; afterAmount: string | null;
    beforeVersionId: string | null; afterVersionId: string | null;
    changedFields: string[];
    comparison: Record<string, unknown> | null;
  };
  links: { permalink: string; sourceUrl: string | null };
  evidenceIds: string[];
}

export interface ItemEntity extends ChangeEntity {
  revisionHistory: { revision: number; revisedAt: string | null; reason: string | null }[];
}

export interface PriceEntity {
  id: string;
  factKey: string;
  providerId: string;
  sourceId: string;
  modelKey: string;
  /** Task 07 T07-3：可选 model identity（unresolved/pointer 不写——零伪造） */
  modelId?: string;
  modelName?: string;
  familyId?: string;
  familyName?: string;
  component: string;
  amount: string;
  currency: string;
  unitQuantity: number;
  unitName: string;
  region: string;
  billingMode: string;
  serviceTier: string;
  contextBand: Record<string, unknown> | null;
  timeCondition: Record<string, unknown> | null;
  effectiveAt: string | null;
  observedAt: string;
  evidenceId: string | null;
  evidenceStatus: string;
  quality: { state: string; reason: string | null; lastSuccessAt: string | null };
  links: { itemPermalink: string | null };
}

export interface EvidenceEntity {
  id: string;
  sourceId: string;
  providerId: string | null;
  sourceUrl: string | null;
  subpageUrl: string | null;
  observedAtRange: [string, string] | null;
  locatorType: string;
  locator: string;
  extractorVersion: string;
  excerptText: string;
  excerptHash: string;
  contentHash: string;
  completeness: string;
  reasons: string[];
  relatedFactIds: string[];
}

export interface WeeklyEntity {
  id: string;
  title: string;
  date: string;
  period: string | null;
  url: string;
  headline: unknown[];
  platforms: unknown[];
  summary_table: unknown;
  trends: unknown[];
  watchpoints: unknown;
  event_index: unknown;
}

export interface StatusEntity {
  providers: { providerId: string; displayName: string; region: string }[];
  sourceStreams: {
    sourceId: string; providerId: string | null; state: string;
    lastAttemptDate: string | null; lastSuccessDate: string | null; reason: string | null;
  }[];
  priceStreams: {
    sourceKey: string; sourceId: string; providerId: string; state: string;
    coverage: string; lastAttemptAt: string | null; lastSuccessAt: string | null;
    reason: string | null;
  }[];
  weekly: { count: number; latestId: string | null };
  counts: Record<string, number>;
}

export class DatasetError extends Error {}

const RELEASE_PATH_RE = /^releases\/ds_[0-9a-f]{64}\/[a-z]+\.json$/;
const DS_RE = /^ds_[0-9a-f]{64}$/;

export class Dataset {
  readonly version: string;
  readonly dataThrough: string;
  readonly generatedAt: string;
  readonly coverage: Record<string, unknown>;
  readonly manifest: Manifest;

  readonly changes: ChangeEntity[];        // 排序：日期倒序 + id 升序
  readonly itemsById: Map<string, ItemEntity>;
  readonly prices: PriceEntity[];          // 排序：provider/model/component/factKey
  readonly evidenceById: Map<string, EvidenceEntity>;
  readonly weekly: WeeklyEntity[];         // 排序：date 升序
  readonly status: StatusEntity;

  readonly enums: {
    providers: Set<string>;
    changeTypes: Set<string>;
    components: Set<string>;
    billingModes: Set<string>;
    regions: Set<string>;
  };

  private constructor(
    manifest: Manifest,
    changes: ChangeEntity[],
    items: ItemEntity[],
    prices: PriceEntity[],
    evidence: EvidenceEntity[],
    weekly: WeeklyEntity[],
    status: StatusEntity,
  ) {
    this.manifest = manifest;
    this.version = manifest.datasetVersion;
    this.dataThrough = manifest.dataThrough;
    this.generatedAt = manifest.generatedAt;
    this.coverage = manifest.coverage;
    this.changes = changes;
    this.itemsById = new Map(items.map((i) => [i.id, i]));
    this.prices = prices;
    this.evidenceById = new Map(evidence.map((e) => [e.id, e]));
    this.weekly = weekly;
    this.status = status;
    this.enums = {
      providers: new Set(status.providers.map((p) => p.providerId)),
      changeTypes: new Set(changes.map((c) => c.changeType)),
      components: new Set(prices.map((p) => p.component)),
      billingModes: new Set(prices.map((p) => p.billingMode)),
      regions: new Set(prices.map((p) => p.region)),
    };
  }

  static load(root: string, version?: string): Dataset {
    const rootAbs = path.resolve(root);
    const manifestPath = path.join(rootAbs, 'manifest.json');
    let manifest: Manifest;
    try {
      manifest = JSON.parse(readFileSync(manifestPath, 'utf-8')) as Manifest;
    } catch (e) {
      throw new DatasetError(`manifest 不可读: ${manifestPath}: ${(e as Error).message}`);
    }
    if (manifest.schemaVersion !== SCHEMA_VERSION) {
      throw new DatasetError(`manifest schemaVersion 非法: ${manifest.schemaVersion}`);
    }
    if (!DS_RE.test(manifest.datasetVersion ?? '')) {
      throw new DatasetError('manifest datasetVersion 非法');
    }
    if (version !== undefined && manifest.datasetVersion !== version) {
      // manifest 已切换：尝试直接读旧 release 目录（cursor 固定版本）
      return Dataset.loadDirect(rootAbs, version);
    }
    const changes = Dataset.readArr<ChangeEntity[]>(rootAbs, manifest, 'changes');
    const items = Dataset.readArr<ItemEntity[]>(rootAbs, manifest, 'items');
    const prices = Dataset.readArr<PriceEntity[]>(rootAbs, manifest, 'prices');
    const evidence = Dataset.readArr<EvidenceEntity[]>(rootAbs, manifest, 'evidence');
    const weekly = Dataset.readArr<WeeklyEntity[]>(rootAbs, manifest, 'weekly');
    const status = Dataset.readArr<StatusEntity>(rootAbs, manifest, 'status');
    Dataset.spotCheck(changes, prices, evidence, weekly, status);
    return new Dataset(manifest, changes, items, prices, evidence, weekly, status);
  }

  /** 直接加载指定版本（cursor 固定版本）。
   *
   * 验收 P1-1：历史版本与当前版本执行相同的完整性校验——读该 release
   * 自带的 manifest.json（exporter 为每个 release 写入），逐文件比对
   * bytes/SHA-256、路径安全与结构 spot-check；元数据（generatedAt/
   * dataThrough/coverage）取自 release 自身，不丢失。篡改任一文件 →
   * DatasetError（调用方转 409 dataset_version_expired——不可信的历史
   * release 与已清理同等对待，不服务 TAMPERED 内容）。
   */
  static loadDirect(rootAbs: string, version: string): Dataset {
    if (!DS_RE.test(version)) throw new DatasetError(`datasetVersion 非法: ${version}`);
    const dir = path.join(rootAbs, 'releases', version);
    if (!path.resolve(dir).startsWith(rootAbs + path.sep)) {
      throw new DatasetError(`路径越界: ${dir}`);
    }
    // release 自带 manifest
    let manifest: Manifest;
    try {
      manifest = JSON.parse(readFileSync(path.join(dir, 'manifest.json'), 'utf-8')) as Manifest;
    } catch {
      throw new DatasetError(`release manifest 不可读: ${version}`);
    }
    if (manifest.datasetVersion !== version) {
      throw new DatasetError(`release manifest 版本不一致: ${version}`);
    }
    const names = ['changes', 'items', 'prices', 'evidence', 'weekly', 'status'] as const;
    const data: Record<string, unknown> = {};
    for (const n of names) {
      const entry = manifest.files.find(
        (f) => f.path === `releases/${version}/${n}.json`,
      );
      if (!entry) throw new DatasetError(`release manifest 缺文件: ${n}.json`);
      const raw = Dataset.readVerified(rootAbs, entry);
      data[n] = JSON.parse(raw);
    }
    Dataset.spotCheck(
      data['changes'] as ChangeEntity[], data['prices'] as PriceEntity[],
      data['evidence'] as EvidenceEntity[], data['weekly'] as WeeklyEntity[],
      data['status'] as StatusEntity,
    );
    return new Dataset(
      manifest,
      data['changes'] as ChangeEntity[],
      data['items'] as ItemEntity[],
      data['prices'] as PriceEntity[],
      data['evidence'] as EvidenceEntity[],
      data['weekly'] as WeeklyEntity[],
      data['status'] as StatusEntity,
    );
  }

  private static readArr<T>(rootAbs: string, manifest: Manifest, name: string): T {
    const entry = manifest.files.find((f) => f.path === `releases/${manifest.datasetVersion}/${name}.json`);
    if (!entry) throw new DatasetError(`manifest 缺文件: ${name}.json`);
    const raw = Dataset.readVerified(rootAbs, entry);
    return JSON.parse(raw) as T;
  }

  private static readOne<T>(rootAbs: string, manifest: Manifest, name: string): T {
    return Dataset.readArr<T>(rootAbs, manifest, name);
  }

  private static readVerified(rootAbs: string, entry: ManifestFileEntry): string {
    if (!RELEASE_PATH_RE.test(entry.path)) {
      throw new DatasetError(`manifest 路径非法: ${entry.path}`);
    }
    const p = path.resolve(rootAbs, entry.path);
    if (!p.startsWith(rootAbs + path.sep)) {
      throw new DatasetError(`路径越界: ${entry.path}`);
    }
    let raw: Buffer;
    try {
      const st = statSync(p);
      if (!st.isFile() || st.isSymbolicLink?.()) {
        throw new DatasetError(`非普通文件: ${entry.path}`);
      }
      raw = readFileSync(p);
    } catch (e) {
      if (e instanceof DatasetError) throw e;
      throw new DatasetError(`文件不可读: ${entry.path}`);
    }
    if (raw.length !== entry.bytes) {
      throw new DatasetError(`bytes 不符: ${entry.path} ${raw.length} != ${entry.bytes}`);
    }
    const sha = createHash('sha256').update(raw).digest('hex');
    if (sha !== entry.sha256) {
      throw new DatasetError(`sha256 不符: ${entry.path}`);
    }
    return raw.toString('utf-8');
  }

  private static spotCheck(
    changes: ChangeEntity[], prices: PriceEntity[],
    evidence: EvidenceEntity[], weekly: WeeklyEntity[], status: StatusEntity,
  ): void {
    if (!Array.isArray(changes) || changes.length === 0 && prices.length === 0) {
      throw new DatasetError('changes 与 prices 均为空（疑似坏 release）');
    }
    if (!status?.providers?.length) throw new DatasetError('status.providers 为空');
    // 排序 spot-check（首尾）
    if (changes.length >= 2) {
      const a = changes[0]!;
      const b = changes[1]!;
      if (a.observationDate < b.observationDate) {
        throw new DatasetError('changes 排序错误（非日期倒序）');
      }
    }
    if (!Array.isArray(evidence) || !Array.isArray(weekly)) {
      throw new DatasetError('evidence/weekly 非数组');
    }
  }
}

export class DatasetHolder {
  #current: Dataset | null = null;
  #retained: Map<string, Dataset> = new Map();
  #root: string;
  lastReloadError: string | null = null;
  lastReloadAt: string | null = null;

  constructor(root: string) {
    this.#root = root;
  }

  get current(): Dataset | null {
    return this.#current;
  }

  /** 启动/重载：加载成功原子替换；失败保留旧版并记录。 */
  reload(): boolean {
    try {
      const ds = Dataset.load(this.#root);
      this.#current = ds;
      this.lastReloadError = null;
      this.lastReloadAt = new Date().toISOString();
      // 清理 retained 中不在保留集的版本（此后其 cursor → 409）
      const keep = new Set<string>(
        [ds.version, ...(ds.manifest.retainedVersions ?? []).map((r) => r.datasetVersion)],
      );
      for (const v of [...this.#retained.keys()]) {
        if (!keep.has(v)) this.#retained.delete(v);
      }
      return true;
    } catch (e) {
      this.lastReloadError = (e as Error).message;
      this.lastReloadAt = new Date().toISOString();
      return false;
    }
  }

  /** cursor 固定版本：优先 retained，其次磁盘直读；不可得 → null（409）。 */
  getOrLoad(version: string): Dataset | null {
    if (this.#current?.version === version) return this.#current;
    const cached = this.#retained.get(version);
    if (cached) return cached;
    try {
      const ds = Dataset.loadDirect(path.resolve(this.#root), version);
      this.#retained.set(version, ds);
      return ds;
    } catch {
      return null;
    }
  }
}
