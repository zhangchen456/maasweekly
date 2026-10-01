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
import { readFileSync, lstatSync, realpathSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { loadDatasetInWorker } from './dataset-loader.js';
import path from 'node:path';

export const SCHEMA_VERSION = '1.0';

export interface ModelIdentityCatalog {
  models: { modelId: string; modelName: string; familyId?: string; familyName?: string }[];
  families: { familyId: string; familyName: string }[];
}

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
  /** Task 07 T07-3：可选 model identity（unresolved/pointer 不写——零伪造）。
   * price_change 透过 price.modelId 间接携带；source_observation 无。 */
  modelId?: string | null;
  modelName?: string | null;
  familyId?: string | null;
  familyName?: string | null;
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

const RELEASE_PATH_RE = /^releases\/ds_[0-9a-f]{64}\/[a-z]+(?:-[a-z]+)*\.json$/;
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
  readonly weeklyDescending: WeeklyEntity[];
  readonly status: StatusEntity;

  /** Task 07 T07-3：identity catalog（from release 的 model-identities.json） */
  readonly modelIdentities: ModelIdentityCatalog;
  readonly changesByProvider = new Map<string, ChangeEntity[]>();
  readonly changesByModel = new Map<string, ChangeEntity[]>();
  readonly changesByFamily = new Map<string, ChangeEntity[]>();
  readonly pricesByProvider = new Map<string, PriceEntity[]>();
  readonly pricesByModel = new Map<string, PriceEntity[]>();
  readonly pricesByFamily = new Map<string, PriceEntity[]>();

  readonly enums: {
    providers: Set<string>;
    changeTypes: Set<string>;
    components: Set<string>;
    billingModes: Set<string>;
    regions: Set<string>;
    /** Task 07 T07-3：合法 model identity 集合（来源：该 release 冻结的 registry catalog，
     * 不在 TS 手工枚举）。unknown modelId/familyId → 400 invalid。
     * pointer/non_model 不得作为合法 modelId filter。 */
    validModelIds: Set<string>;
    validFamilyIds: Set<string>;
  };

  private constructor(
    manifest: Manifest,
    changes: ChangeEntity[],
    items: ItemEntity[],
    prices: PriceEntity[],
    evidence: EvidenceEntity[],
    weekly: WeeklyEntity[],
    status: StatusEntity,
    root: string | ModelIdentityCatalog,
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
    this.weeklyDescending = [...weekly].sort((a, b) => a.date < b.date ? 1 : a.date > b.date ? -1 : 0);
    this.status = status;
    this.modelIdentities = typeof root === 'string' ? Dataset.readIdentityCatalog(root, manifest) : root;
    this.enums = {
      providers: new Set(status.providers.map((p) => p.providerId)),
      changeTypes: new Set(changes.map((c) => c.changeType)),
      components: new Set(prices.map((p) => p.component)),
      billingModes: new Set(prices.map((p) => p.billingMode)),
      regions: new Set(prices.map((p) => p.region)),
      validModelIds: new Set(
        this.modelIdentities.models.map((m) => m.modelId)),
      validFamilyIds: new Set(
        this.modelIdentities.families.map((f) => f.familyId)),
    };
    for (const c of changes) this.indexChange(c);
    for (const p of prices) this.indexPrice(p);
  }

  private group<T>(index: Map<string, T[]>, key: string | null | undefined, value: T): void {
    if (!key) return;
    const values = index.get(key);
    if (values) values.push(value); else index.set(key, [value]);
  }

  private indexChange(c: ChangeEntity): void {
    this.group(this.changesByProvider, c.providerId, c);
    this.group(this.changesByModel, c.modelId, c);
    this.group(this.changesByFamily, c.familyId, c);
    this.enums.changeTypes.add(c.changeType);
  }

  private indexPrice(p: PriceEntity): void {
    this.group(this.pricesByProvider, p.providerId, p);
    this.group(this.pricesByModel, p.modelId, p);
    this.group(this.pricesByFamily, p.familyId, p);
    this.enums.components.add(p.component);
    this.enums.billingModes.add(p.billingMode);
    this.enums.regions.add(p.region);
  }

  /** Only used for the private, validated worker stream; never published partially. */
  static beginStream(manifest: Manifest, catalog: ModelIdentityCatalog, status: StatusEntity, weekly: WeeklyEntity[]): Dataset {
    return new Dataset(manifest, [], [], [], [], weekly, status, catalog);
  }

  appendStream(part: 'changes' | 'items' | 'prices' | 'evidence', values: unknown[]): void {
    switch (part) {
      case 'changes': for (const c of values as ChangeEntity[]) { this.changes.push(c); this.indexChange(c); } break;
      case 'prices': for (const p of values as PriceEntity[]) { this.prices.push(p); this.indexPrice(p); } break;
      case 'items': for (const i of values as ItemEntity[]) this.itemsById.set(i.id, i); break;
      case 'evidence': for (const e of values as EvidenceEntity[]) this.evidenceById.set(e.id, e); break;
    }
  }

  static validateManifest(manifest: Manifest): void {
    if (manifest?.schemaVersion !== SCHEMA_VERSION) throw new DatasetError('manifest schemaVersion 非法');
    if (!DS_RE.test(manifest.datasetVersion ?? '') || !Array.isArray(manifest.files)) throw new DatasetError('manifest 结构非法');
    const paths = new Set<string>();
    for (const f of manifest.files) {
      if (!f || !RELEASE_PATH_RE.test(f.path) || !f.path.startsWith(`releases/${manifest.datasetVersion}/`)
        || paths.has(f.path) || !Number.isSafeInteger(f.bytes) || f.bytes < 0 || !/^[0-9a-f]{64}$/.test(f.sha256)) {
        throw new DatasetError('manifest 文件清单非法或重复');
      }
      paths.add(f.path);
    }
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
    Dataset.validateManifest(manifest);
    if (version !== undefined && manifest.datasetVersion !== version) {
      // manifest 已切换：尝试直接读旧 release 目录（cursor 固定版本）
      return Dataset.loadDirect(rootAbs, version);
    }
    return Dataset.loadManifest(rootAbs, manifest);
  }

  static loadManifest(rootAbs: string, manifest: Manifest): Dataset {
    Dataset.validateManifest(manifest);
    const changes = Dataset.readArr<ChangeEntity[]>(rootAbs, manifest, 'changes');
    const items = Dataset.readArr<ItemEntity[]>(rootAbs, manifest, 'items');
    const prices = Dataset.readArr<PriceEntity[]>(rootAbs, manifest, 'prices');
    const evidence = Dataset.readArr<EvidenceEntity[]>(rootAbs, manifest, 'evidence');
    const weekly = Dataset.readArr<WeeklyEntity[]>(rootAbs, manifest, 'weekly');
    const status = Dataset.readArr<StatusEntity>(rootAbs, manifest, 'status');
    Dataset.spotCheck(changes, prices, evidence, weekly, status);
    if (!Array.isArray(items)) throw new DatasetError('items 非数组');
    const ids = (values: { id: string }[], name: string): Set<string> => {
      const result = new Set<string>();
      for (const value of values) {
        if (!value || typeof value.id !== 'string' || !value.id || result.has(value.id)) throw new DatasetError(`${name} id 非法或重复`);
        result.add(value.id);
      }
      return result;
    };
    const itemIds = ids(items, 'items'), evidenceIds = ids(evidence, 'evidence');
    ids(changes, 'changes'); ids(prices, 'prices'); ids(weekly, 'weekly');
    for (const c of changes) {
      if (!itemIds.has(c.id) || !Array.isArray(c.evidenceIds) || c.evidenceIds.some(id => !evidenceIds.has(id))) {
        throw new DatasetError('changes item/evidence 引用缺失');
      }
    }
    for (const p of prices) if (p.evidenceId != null && !evidenceIds.has(p.evidenceId)) throw new DatasetError('prices evidence 引用缺失');
    const known = new Set(['changes', 'items', 'prices', 'evidence', 'weekly', 'status', 'model-identities'].map(name => `releases/${manifest.datasetVersion}/${name}.json`));
    for (const file of manifest.files) if (!known.has(file.path)) Dataset.readVerified(rootAbs, file);
    return new Dataset(manifest, changes, items, prices, evidence, weekly, status, rootAbs);
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
    Dataset.validateManifest(manifest);
    return Dataset.loadManifest(rootAbs, manifest);
  }

  private static readIdentityCatalog(root: string, manifest: Manifest): ModelIdentityCatalog {
    let raw: unknown;
    try {
      raw = Dataset.readArr<unknown>(root, manifest, 'model-identities');
    } catch (error) {
      throw new DatasetError(`identity catalog 不可读: ${(error as Error).message}`);
    }
    const fail = (): never => { throw new DatasetError('identity catalog 结构非法'); };
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return fail();
    const catalog = raw as ModelIdentityCatalog;
    if (!Array.isArray(catalog.models) || !Array.isArray(catalog.families)) return fail();
    const validId = (v: unknown): v is string =>
      typeof v === 'string' && /^[a-z0-9-]+:[a-z0-9.-]+$/.test(v);
    const validName = (v: unknown): v is string => typeof v === 'string' && v.trim().length > 0;
    const families = new Map<string, string>();
    for (const f of catalog.families) {
      if (!f || !validId(f.familyId) || !validName(f.familyName) || families.has(f.familyId)) return fail();
      families.set(f.familyId, f.familyName);
    }
    const models = new Set<string>();
    for (const m of catalog.models) {
      if (!m || !validId(m.modelId) || !validName(m.modelName) || models.has(m.modelId) || families.has(m.modelId)) return fail();
      if (m.familyId !== undefined || m.familyName !== undefined) {
        if (!validId(m.familyId) || !validName(m.familyName) || !families.has(m.familyId) ||
            families.get(m.familyId) !== m.familyName ||
            m.modelId.split(':')[0] !== m.familyId.split(':')[0]) return fail();
      }
      models.add(m.modelId);
    }
    return catalog;
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
      const st = lstatSync(p);
      if (!st.isFile() || st.isSymbolicLink?.()) {
        throw new DatasetError(`非普通文件: ${entry.path}`);
      }
      if (!realpathSync(p).startsWith(realpathSync(rootAbs) + path.sep)) throw new DatasetError(`路径越界: ${entry.path}`);
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
    if (!Array.isArray(changes) || !Array.isArray(prices) || changes.length === 0 && prices.length === 0) {
      throw new DatasetError('changes 与 prices 均为空（疑似坏 release）');
    }
    if (!status?.providers?.length) throw new DatasetError('status.providers 为空');
    // Binary seek requires the entire sequence to satisfy the frozen order.
    for (let i = 1; i < changes.length; i++) {
      const a = changes[i - 1]!, b = changes[i]!;
      if (a.observationDate < b.observationDate || (a.observationDate === b.observationDate && a.id >= b.id)) {
        throw new DatasetError('changes 排序错误或重复 id');
      }
    }
    for (let i = 1; i < prices.length; i++) {
      const a = prices[i - 1]!, b = prices[i]!;
      const left = [a.providerId, a.modelKey, a.component, a.factKey], right = [b.providerId, b.modelKey, b.component, b.factKey];
      let cmp = 0;
      for (let k = 0; k < left.length; k++) {
        if (left[k]! < right[k]!) { cmp = -1; break; }
        if (left[k]! > right[k]!) { cmp = 1; break; }
      }
      if (cmp >= 0) throw new DatasetError('prices 排序错误或重复 factKey');
    }
    if (!Array.isArray(evidence) || !Array.isArray(weekly)) {
      throw new DatasetError('evidence/weekly 非数组');
    }
  }
}

export interface DatasetHolderOptions {
  maxRetainedVersions?: number;
  maxRetainedBytes?: number;
  loader?: (root: string, manifest: Manifest, signal: AbortSignal) => Promise<Dataset>;
}
export type ReloadResult = 'changed' | 'unchanged' | 'superseded' | 'failed';

export class DatasetHolder {
  #current: Dataset | null = null;
  #retained = new Map<string, Dataset>();
  #root: string;
  #generation = 0;
  #requestSequence = 0;
  #latestCandidateRequest = 0;
  #closed = false;
  #abort = new AbortController();
  #jobs = new Map<string, Promise<Dataset>>();
  #queue: Promise<void> = Promise.resolve();
  #options: Required<DatasetHolderOptions>;
  lastReloadError: string | null = null;
  lastReloadAt: string | null = null;
  readonly metrics = { businessLoads: 0, unchangedPolls: 0, cacheHits: 0, cacheMisses: 0 };

  constructor(root: string, options: DatasetHolderOptions = {}) {
    this.#root = path.resolve(root);
    this.#options = { maxRetainedVersions: 2, maxRetainedBytes: 128 * 1024 * 1024,
      loader: loadDatasetInWorker, ...options };
    if (!Number.isSafeInteger(this.#options.maxRetainedVersions) || this.#options.maxRetainedVersions < 0
      || !Number.isSafeInteger(this.#options.maxRetainedBytes) || this.#options.maxRetainedBytes < 0) {
      throw new DatasetError('invalid retained cache budget');
    }
  }

  get current(): Dataset | null { return this.#current; }
  get cacheState() { return { entries: this.#retained.size, bytes: [...this.#retained.values()].reduce((sum, ds) => sum + this.bytes(ds), 0), inFlight: this.#jobs.size }; }
  private bytes(ds: Dataset): number { return ds.manifest.files.reduce((n, f) => n + f.bytes, 0); }

  private retain(ds: Dataset): void {
    if (ds.version === this.#current?.version) return;
    this.#retained.delete(ds.version);
    this.#retained.set(ds.version, ds);
    while (this.#retained.size > this.#options.maxRetainedVersions || this.cacheState.bytes > this.#options.maxRetainedBytes) {
      this.#retained.delete(this.#retained.keys().next().value!);
    }
  }

  private cached(version: string): Dataset | null {
    if (this.#current?.version === version) return this.#current;
    const ds = this.#retained.get(version);
    if (!ds) return null;
    this.metrics.cacheHits++; this.#retained.delete(version); this.#retained.set(version, ds);
    return ds;
  }

  private accept(ds: Dataset): void {
    this.#current = ds;
    this.#retained.delete(ds.version);
    const keep = new Set([ds.version, ...(ds.manifest.retainedVersions ?? []).map(r => r.datasetVersion)]);
    for (const v of this.#retained.keys()) if (!keep.has(v)) this.#retained.delete(v);
    this.lastReloadError = null; this.lastReloadAt = new Date().toISOString();
  }

  /** Explicit synchronous verification remains available for offline callers/tests. */
  reload(): boolean {
    this.#latestCandidateRequest = ++this.#requestSequence;
    this.#generation++;
    try {
      if (this.#closed) throw new DatasetError('holder closed');
      this.metrics.businessLoads++;
      this.accept(Dataset.load(this.#root)); return true;
    } catch (error) {
      this.lastReloadError = (error as Error).message; this.lastReloadAt = new Date().toISOString(); return false;
    }
  }

  private async manifest(version?: string): Promise<Manifest> {
    const file = version ? path.join(this.#root, 'releases', version, 'manifest.json') : path.join(this.#root, 'manifest.json');
    const manifest = JSON.parse(await readFile(file, 'utf8')) as Manifest;
    Dataset.validateManifest(manifest);
    if (version && manifest.datasetVersion !== version) throw new DatasetError('release manifest version mismatch');
    return manifest;
  }

  private load(manifest: Manifest): Promise<Dataset> {
    const existing = this.#jobs.get(manifest.datasetVersion);
    if (existing) return existing;
    const job = this.#queue.then(async () => {
      if (this.#closed) throw new DatasetError('holder closed');
      this.metrics.businessLoads++;
      return this.#options.loader(this.#root, manifest, this.#abort.signal);
    });
    this.#jobs.set(manifest.datasetVersion, job);
    const clear = () => { if (this.#jobs.get(manifest.datasetVersion) === job) this.#jobs.delete(manifest.datasetVersion); };
    void job.then(clear, clear);
    this.#queue = job.then(() => undefined, () => undefined);
    return job;
  }

  /** Poll only metadata; SIGHUP passes force=true to reverify an immutable version. */
  async reloadAsync({ force = false }: { force?: boolean } = {}): Promise<ReloadResult> {
    const request = ++this.#requestSequence;
    let generation = this.#generation;
    try {
      if (this.#closed) throw new DatasetError('holder closed');
      const manifest = await this.manifest();
      if (this.#closed) return 'superseded';
      if (manifest.datasetVersion === this.#current?.version && !force) {
        this.metrics.unchangedPolls++; return 'unchanged';
      }
      if (this.#closed || request < this.#latestCandidateRequest) return 'superseded';
      this.#latestCandidateRequest = request; generation = ++this.#generation;
      const ds = await this.load(manifest);
      const latest = await this.manifest();
      if (generation !== this.#generation || this.#closed || latest.datasetVersion !== ds.version) return 'superseded';
      this.accept(ds); return 'changed';
    } catch (error) {
      if (generation !== this.#generation) return 'superseded';
      this.lastReloadError = (error as Error).message; this.lastReloadAt = new Date().toISOString(); return 'failed';
    }
  }

  getOrLoad(version: string): Dataset | null {
    const cached = this.cached(version); if (cached) return cached;
    if (!DS_RE.test(version) || this.#closed) return null;
    this.metrics.cacheMisses++;
    try {
      this.metrics.businessLoads++;
      const ds = Dataset.loadDirect(this.#root, version); this.retain(ds); return ds;
    } catch { return null; }
  }

  async getOrLoadAsync(version: string): Promise<Dataset | null> {
    const cached = this.cached(version); if (cached) return cached;
    if (!DS_RE.test(version) || this.#closed) return null;
    this.metrics.cacheMisses++;
    try {
      const ds = await this.load(await this.manifest(version)); this.retain(ds); return ds;
    } catch { return null; }
  }

  close(): void { this.#closed = true; this.#generation++; this.#abort.abort(); }
}
