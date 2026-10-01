// Generated bridge; canonical source: packages/public-contract/validation.ts
import { SCHEMA_VERSION, type Manifest, type ModelIdentityCatalog, type ChangeEntity, type PriceEntity, type ItemEntity, type EvidenceEntity, type WeeklyEntity, type StatusEntity } from './entities.js';
export class DatasetError extends Error {}
export const RELEASE_PATH_RE = /^releases\/ds_[0-9a-f]{64}\/[a-z]+(?:-[a-z]+)*\.json$/;
export const DS_RE = /^ds_[0-9a-f]{64}$/;
export function validateManifest(manifest: Manifest): void {
    if (manifest?.schemaVersion !== SCHEMA_VERSION) throw new DatasetError('manifest schemaVersion 非法');
    if (!DS_RE.test(manifest.datasetVersion ?? '') || !Array.isArray(manifest.files)) throw new DatasetError('manifest datasetVersion/files 结构非法');
    const paths = new Set<string>();
    for (const f of manifest.files) {
      if (!f || typeof f.path !== 'string' || !RELEASE_PATH_RE.test(f.path) || !f.path.startsWith(`releases/${manifest.datasetVersion}/`)) throw new DatasetError('manifest 文件路径越界或逃逸');
      if (!f || !RELEASE_PATH_RE.test(f.path) || !f.path.startsWith(`releases/${manifest.datasetVersion}/`)
        || paths.has(f.path) || !Number.isSafeInteger(f.bytes) || f.bytes < 1 || !/^[0-9a-f]{64}$/.test(f.sha256)) {
        throw new DatasetError('manifest 文件清单非法或重复');
      }
      paths.add(f.path);
    }
    for (const name of ["changes", "items", "prices", "evidence", "weekly", "status", "model-identities"]) {
      if (!paths.has(`releases/${manifest.datasetVersion}/${name}.json`)) throw new DatasetError(`请求加载的文件不在 manifest 清单: ${name === "model-identities" ? "identity catalog " : ""}${name}.json`);
    }
}
export function validateIdentityCatalog(raw: unknown): ModelIdentityCatalog {
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
    return catalog;}
export function validateCollections(changes: ChangeEntity[], items: ItemEntity[], prices: PriceEntity[], evidence: EvidenceEntity[], weekly: WeeklyEntity[], status: StatusEntity): void {
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
}
