/**
 * 测试夹具：临时目录手写微型 release（Task 03 T06–T17）。
 * datasetVersion 可任取合法 hex——服务端只校验 hash，不重算版本。
 */
import { mkdirSync, writeFileSync, rmSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';

export interface FixtureChange {
  id: string;
  observationDate: string;
  providerId?: string | null;
  recordType?: string;
  status?: string;
  title?: string;
  summary?: string | null;
  model?: string;
  changeType?: string;
  evidenceId?: string;
}

export interface FixturePrice {
  factKey: string;
  providerId: string;
  modelKey: string;
  component: string;
  amount?: string;
  currency?: string;
  region?: string;
  billingMode?: string;
  contextBand?: object | null;
  timeCondition?: object | null;
}

export class ReleaseFixture {
  root: string;

  constructor(root: string) {
    this.root = root;
  }

  /** 写一套完整 release（覆盖指定版本目录），并更新 manifest。 */
  writeRelease(version: string, opts: {
    changes?: FixtureChange[];
    prices?: FixturePrice[];
    weekly?: string[];
    tamper?: 'hash' | null;
  } = {}): void {
    const dir = path.join(this.root, 'releases', version);
    mkdirSync(dir, { recursive: true });
    const changes = (opts.changes ?? []).map((c) => ({
      id: c.id,
      revision: 1,
      status: c.status ?? 'active',
      recordType: c.recordType ?? 'source_observation',
      providerId: c.providerId ?? 'openai',
      sourceId: 'openai-blog',
      sourceType: 'blog',
      observedAt: null,
      observationDate: c.observationDate,
      timePrecision: 'date',
      publishedAt: null,
      updatedAt: null,
      title: c.title ?? `记录 ${c.id}`,
      summary: c.summary ?? null,
      summaryOrigin: null,
      changeType: c.changeType ?? 'source_updated',
      evidenceLevel: c.recordType === 'price_change' ? 'fact_versions' : 'source_diff',
      quality: { state: 'fresh', reason: null, lastSuccessAt: null },
      ...(c.recordType === 'price_change' ? {
        price: {
          factKey: c.model ?? 'fk1', model: c.model ?? 'm1', component: 'input',
          currency: 'USD', unitQuantity: 1000000, unitName: 'token',
          region: 'global', billingMode: 'realtime', serviceTier: 'standard',
          contextBand: null, timeCondition: null,
          beforeAmount: null, afterAmount: '1.000000',
          beforeVersionId: null, afterVersionId: 'pfv_' + 'a'.repeat(64),
          changedFields: [], comparison: null,
        },
        links: { permalink: `/item/${c.id}/`, sourceUrl: 'https://example.com' },
        evidenceIds: c.evidenceId ? [c.evidenceId] : [],
      } : {
        diff: { addedLines: [], removedLines: [], addedCount: 0, removedCount: 0, completeness: null },
        links: { permalink: `/item/${c.id}/`, sourceUrl: 'https://example.com' },
        evidenceIds: [],
      }),
    }));
    const items = changes.map((c) => ({
      ...c, revisionHistory: [{ revision: 1, revisedAt: null, reason: null }],
    }));
    // changes 必须按规范排序（日期倒序 + id 升序）——keyset 分页的前提
    changes.sort((x, y) =>
      y.observationDate.localeCompare(x.observationDate) || x.id.localeCompare(y.id));
    const prices = (opts.prices ?? []).map((p) => ({
      id: 'pfv_' + createHash('sha256').update(p.factKey).digest('hex'),
      factKey: p.factKey,
      providerId: p.providerId,
      sourceId: `${p.providerId}-pricing`,
      modelKey: p.modelKey,
      component: p.component,
      amount: p.amount ?? '1.000000',
      currency: p.currency ?? 'USD',
      unitQuantity: 1000000,
      unitName: 'token',
      region: p.region ?? 'global',
      billingMode: p.billingMode ?? 'realtime',
      serviceTier: 'standard',
      contextBand: p.contextBand ?? null,
      timeCondition: p.timeCondition ?? null,
      effectiveAt: null,
      observedAt: `${(opts.changes ?? [])[0]?.observationDate ?? '2026-09-10'}T00:00:00Z`,
      evidenceId: null,
      evidenceStatus: 'complete',
      quality: { state: 'fresh', reason: null, lastSuccessAt: null },
      links: { itemPermalink: null },
    }));
    const evidenceIds = new Set(changes.flatMap((c) => (c as { evidenceIds?: string[] }).evidenceIds ?? []));
    const evidence = [...evidenceIds].map((eid) => ({
      id: eid,
      sourceId: 'openai-pricing',
      providerId: 'openai',
      sourceUrl: 'https://example.com/p',
      subpageUrl: null,
      observedAtRange: null,
      locatorType: 'dom_selector',
      locator: 'table:nth-of-type(1)',
      extractorVersion: 'test-1',
      excerptText: 'EVIL<script>alert("xss")</script>END $1 / 1M tokens',
      excerptHash: 'a'.repeat(64),
      contentHash: 'b'.repeat(64),
      completeness: 'complete',
      reasons: [],
      relatedFactIds: [],
    }));
    const weeklyDates = opts.weekly ?? ['2026-09-01', '2026-08-25'];
    const weekly = weeklyDates.map((d) => ({
      id: d, title: `周报 ${d}`, date: d, period: null,
      url: `/weekly/${d}/`, headline: [], platforms: [], summary_table: null,
      trends: [], watchpoints: null, event_index: null,
    }));
    const status = {
      providers: [
        { providerId: 'openai', displayName: 'OpenAI', region: 'overseas' },
        { providerId: 'alibaba', displayName: '阿里百炼', region: 'china' },
      ],
      sourceStreams: [{ sourceId: 'openai-blog', providerId: 'openai', state: 'ok',
                        lastAttemptDate: '2026-09-16', lastSuccessDate: '2026-09-16', reason: null }],
      priceStreams: [{ sourceKey: 'openai:pricing', sourceId: 'openai-pricing',
                       providerId: 'openai', state: 'ok', coverage: 'full',
                       lastAttemptAt: '2026-09-16T02:00:00Z',
                       lastSuccessAt: '2026-09-16T02:00:00Z', reason: null }],
      weekly: { count: weekly.length, latestId: weeklyDates.at(-1) ?? null },
      counts: { changes: changes.length, prices: prices.length,
                evidence: evidence.length, weekly: weekly.length },
    };
    const files: { path: string; sha256: string; bytes: number }[] = [];
    const write = (name: string, payload: unknown): void => {
      const text = JSON.stringify(payload);
      const data = Buffer.from(text, 'utf-8');
      writeFileSync(path.join(dir, name), data);
      const sha = createHash('sha256').update(data).digest('hex');
      files.push({
        path: `releases/${version}/${name}`,
        sha256: opts.tamper === 'hash' && name === 'status.json' ? '0'.repeat(64) : sha,
        bytes: data.length,
      });
    };
    write('changes.json', changes);
    write('items.json', items);
    write('prices.json', prices);
    write('evidence.json', evidence);
    write('weekly.json', weekly);
    write('status.json', status);
    // per-release manifest（P1-1：历史版本同校验的数据源）
    writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify({
      schemaVersion: '1.0',
      datasetVersion: version,
      generatedAt: '2026-09-16T00:00:00Z',
      dataThrough: '2026-09-16',
      coverage: {},
      files,
      retainedVersions: [],
    }));
    // manifest
    const oldManifest = this.readManifestOrNull();
    const retained = oldManifest
      ? [oldManifest, ...(oldManifest.retainedVersions ?? [])]
      : [];
    const prevRetained = retained.slice(0, 1).map((m: { datasetVersion: string; generatedAt: string }) => ({
      datasetVersion: m.datasetVersion,
      generatedAt: m.generatedAt,
    }));
    writeFileSync(path.join(this.root, 'manifest.json'), JSON.stringify({
      schemaVersion: '1.0',
      datasetVersion: version,
      generatedAt: '2026-09-16T00:00:00Z',
      dataThrough: '2026-09-16',
      coverage: {},
      files,
      retainedVersions: [
        { datasetVersion: version, generatedAt: '2026-09-16T00:00:00Z' },
        ...prevRetained,
      ],
    }));
  }

  readManifestOrNull(): { datasetVersion: string; generatedAt: string;
                           retainedVersions?: { datasetVersion: string; generatedAt: string }[] } | null {
    try {
      return JSON.parse(readFileSync(path.join(this.root, 'manifest.json'), 'utf-8'));
    } catch {
      return null;
    }
  }

  cleanup(): void {
    rmSync(this.root, { recursive: true, force: true });
  }
}
