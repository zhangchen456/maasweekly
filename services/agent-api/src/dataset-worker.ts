import { parentPort, workerData } from 'node:worker_threads';
import { once } from 'node:events';
import { Dataset, type Manifest } from './dataset.js';

const port = parentPort!;
try {
  const { root, manifest } = workerData as { root: string; manifest: Manifest };
  const ds = Dataset.loadManifest(root, manifest);
  port.postMessage({ kind: 'meta', manifest: ds.manifest, catalog: ds.modelIdentities,
    status: ds.status, weekly: ds.weekly,
    counts: { changes: ds.changes.length, prices: ds.prices.length, items: ds.itemsById.size, evidence: ds.evidenceById.size } });
  await once(port, 'message');
  const parts = { changes: ds.changes, prices: ds.prices, items: [...ds.itemsById.values()], evidence: [...ds.evidenceById.values()] };
  for (const [part, values] of Object.entries(parts)) {
    for (let i = 0; i < values.length; i += 200) {
      port.postMessage({ kind: 'chunk', part, values: values.slice(i, i + 200) });
      // Backpressure: a bounded message is hydrated on a separate main-loop turn.
      await once(port, 'message');
    }
  }
  port.postMessage({ kind: 'done' });
} catch (error) {
  port.postMessage({ kind: 'error', message: (error as Error).message });
} finally {
  port.close();
}
