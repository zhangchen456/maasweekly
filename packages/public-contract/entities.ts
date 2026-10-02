import type { ChangeDTO, PriceDTO, EvidenceDTO, WeeklyDTO, ManifestDTO, ModelIdentityCatalogDTO } from './schema-dto.js';
export const SCHEMA_VERSION = '1.0';

export interface ModelIdentityCatalog extends ModelIdentityCatalogDTO {
  models: { modelId: string; modelName: string; familyId?: string; familyName?: string }[];
  families: { familyId: string; familyName: string }[];
}

export interface ManifestFileEntry {
  path: string;
  sha256: string;
  bytes: number;
}
export interface Manifest extends Pick<ManifestDTO, 'schemaVersion' | 'datasetVersion' | 'generatedAt' | 'dataThrough'> {
  schemaVersion: "1.0";
  datasetVersion: string;
  generatedAt: string;
  dataThrough: string;
  coverage: Record<string, unknown>;
  files: ManifestFileEntry[];
  retainedVersions: { datasetVersion: string; generatedAt: string }[];
}

export interface ChangeEntity extends Pick<ChangeDTO, 'id' | 'revision' | 'status' | 'recordType'> {
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

export interface PriceEntity extends Pick<PriceDTO, 'id' | 'factKey' | 'amount'> {
  id: string;
  factKey: string;
  providerId: string;
  sourceId: string;
  modelKey: string;
  platformId?: string;
  upstreamModelId?: string;
  availabilityId?: string;
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

export interface EvidenceEntity extends Pick<EvidenceDTO, 'id'> {
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

export interface WeeklyEntity extends Pick<WeeklyDTO, 'id' | 'date' | 'url'> {
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

