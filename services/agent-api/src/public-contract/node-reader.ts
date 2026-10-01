// Generated bridge; canonical source: packages/public-contract/node-reader.ts
/** Server/build-only filesystem boundary; do not import from browser code. */
import { createHash } from 'node:crypto';
import { readFileSync, lstatSync, realpathSync } from 'node:fs';
import path from 'node:path';
import type { ManifestFileEntry } from './entities.js';
import { DatasetError, RELEASE_PATH_RE } from './validation.js';
export function readVerified(rootAbs: string, entry: ManifestFileEntry): string {
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
    return raw.toString('utf-8');}
