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
export class DatasetError extends Error {
}
const RELEASE_PATH_RE = /^releases\/ds_[0-9a-f]{64}\/[a-z]+\.json$/;
const DS_RE = /^ds_[0-9a-f]{64}$/;
export class Dataset {
    version;
    dataThrough;
    generatedAt;
    coverage;
    manifest;
    changes; // 排序：日期倒序 + id 升序
    itemsById;
    prices; // 排序：provider/model/component/factKey
    evidenceById;
    weekly; // 排序：date 升序
    status;
    enums;
    constructor(manifest, changes, items, prices, evidence, weekly, status) {
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
    static load(root, version) {
        const rootAbs = path.resolve(root);
        const manifestPath = path.join(rootAbs, 'manifest.json');
        let manifest;
        try {
            manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
        }
        catch (e) {
            throw new DatasetError(`manifest 不可读: ${manifestPath}: ${e.message}`);
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
        const changes = Dataset.readArr(rootAbs, manifest, 'changes');
        const items = Dataset.readArr(rootAbs, manifest, 'items');
        const prices = Dataset.readArr(rootAbs, manifest, 'prices');
        const evidence = Dataset.readArr(rootAbs, manifest, 'evidence');
        const weekly = Dataset.readArr(rootAbs, manifest, 'weekly');
        const status = Dataset.readArr(rootAbs, manifest, 'status');
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
    static loadDirect(rootAbs, version) {
        if (!DS_RE.test(version))
            throw new DatasetError(`datasetVersion 非法: ${version}`);
        const dir = path.join(rootAbs, 'releases', version);
        if (!path.resolve(dir).startsWith(rootAbs + path.sep)) {
            throw new DatasetError(`路径越界: ${dir}`);
        }
        // release 自带 manifest
        let manifest;
        try {
            manifest = JSON.parse(readFileSync(path.join(dir, 'manifest.json'), 'utf-8'));
        }
        catch {
            throw new DatasetError(`release manifest 不可读: ${version}`);
        }
        if (manifest.datasetVersion !== version) {
            throw new DatasetError(`release manifest 版本不一致: ${version}`);
        }
        const names = ['changes', 'items', 'prices', 'evidence', 'weekly', 'status'];
        const data = {};
        for (const n of names) {
            const entry = manifest.files.find((f) => f.path === `releases/${version}/${n}.json`);
            if (!entry)
                throw new DatasetError(`release manifest 缺文件: ${n}.json`);
            const raw = Dataset.readVerified(rootAbs, entry);
            data[n] = JSON.parse(raw);
        }
        Dataset.spotCheck(data['changes'], data['prices'], data['evidence'], data['weekly'], data['status']);
        return new Dataset(manifest, data['changes'], data['items'], data['prices'], data['evidence'], data['weekly'], data['status']);
    }
    static readArr(rootAbs, manifest, name) {
        const entry = manifest.files.find((f) => f.path === `releases/${manifest.datasetVersion}/${name}.json`);
        if (!entry)
            throw new DatasetError(`manifest 缺文件: ${name}.json`);
        const raw = Dataset.readVerified(rootAbs, entry);
        return JSON.parse(raw);
    }
    static readOne(rootAbs, manifest, name) {
        return Dataset.readArr(rootAbs, manifest, name);
    }
    static readVerified(rootAbs, entry) {
        if (!RELEASE_PATH_RE.test(entry.path)) {
            throw new DatasetError(`manifest 路径非法: ${entry.path}`);
        }
        const p = path.resolve(rootAbs, entry.path);
        if (!p.startsWith(rootAbs + path.sep)) {
            throw new DatasetError(`路径越界: ${entry.path}`);
        }
        let raw;
        try {
            const st = statSync(p);
            if (!st.isFile() || st.isSymbolicLink?.()) {
                throw new DatasetError(`非普通文件: ${entry.path}`);
            }
            raw = readFileSync(p);
        }
        catch (e) {
            if (e instanceof DatasetError)
                throw e;
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
    static spotCheck(changes, prices, evidence, weekly, status) {
        if (!Array.isArray(changes) || changes.length === 0 && prices.length === 0) {
            throw new DatasetError('changes 与 prices 均为空（疑似坏 release）');
        }
        if (!status?.providers?.length)
            throw new DatasetError('status.providers 为空');
        // 排序 spot-check（首尾）
        if (changes.length >= 2) {
            const a = changes[0];
            const b = changes[1];
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
    #current = null;
    #retained = new Map();
    #root;
    lastReloadError = null;
    lastReloadAt = null;
    constructor(root) {
        this.#root = root;
    }
    get current() {
        return this.#current;
    }
    /** 启动/重载：加载成功原子替换；失败保留旧版并记录。 */
    reload() {
        try {
            const ds = Dataset.load(this.#root);
            this.#current = ds;
            this.lastReloadError = null;
            this.lastReloadAt = new Date().toISOString();
            // 清理 retained 中不在保留集的版本（此后其 cursor → 409）
            const keep = new Set([ds.version, ...(ds.manifest.retainedVersions ?? []).map((r) => r.datasetVersion)]);
            for (const v of [...this.#retained.keys()]) {
                if (!keep.has(v))
                    this.#retained.delete(v);
            }
            return true;
        }
        catch (e) {
            this.lastReloadError = e.message;
            this.lastReloadAt = new Date().toISOString();
            return false;
        }
    }
    /** cursor 固定版本：优先 retained，其次磁盘直读；不可得 → null（409）。 */
    getOrLoad(version) {
        if (this.#current?.version === version)
            return this.#current;
        const cached = this.#retained.get(version);
        if (cached)
            return cached;
        try {
            const ds = Dataset.loadDirect(path.resolve(this.#root), version);
            this.#retained.set(version, ds);
            return ds;
        }
        catch {
            return null;
        }
    }
}
