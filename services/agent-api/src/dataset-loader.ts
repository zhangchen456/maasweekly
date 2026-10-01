import { Worker } from 'node:worker_threads';
import { Dataset, DatasetError, type Manifest } from './dataset.js';

/** Parse/hash off-thread, then hydrate at most 200 entities per event-loop turn. */
export function loadDatasetInWorker(root: string, manifest: Manifest, signal: AbortSignal): Promise<Dataset> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DatasetError('loader closed')); return; }
    const worker = new Worker(new URL('./dataset-worker.js', import.meta.url), { workerData: { root, manifest } });
    let candidate: Dataset | undefined;
    let counts: Record<string, number>;
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true; clearTimeout(timer); signal.removeEventListener('abort', abort);
      void worker.terminate();
      if (error) reject(error); else resolve(candidate!);
    };
    const abort = () => finish(new DatasetError('loader closed'));
    const timer = setTimeout(() => finish(new DatasetError('dataset loader timeout')), 120000);
    timer.unref(); signal.addEventListener('abort', abort, { once: true });
    worker.on('error', error => finish(error));
    worker.on('exit', () => { if (!settled) finish(new DatasetError('dataset worker exited before completion')); });
    worker.on('message', message => {
      if (settled) return;
      setImmediate(() => {
        if (settled) return;
        try {
          if (message.kind === 'error') { finish(new DatasetError(message.message)); return; }
          if (message.kind === 'meta') {
            candidate = Dataset.beginStream(message.manifest, message.catalog, message.status, message.weekly);
            counts = message.counts;
          } else if (message.kind === 'chunk') {
            if (!candidate || !['changes', 'prices', 'items', 'evidence'].includes(message.part)) throw new DatasetError('invalid dataset stream');
            candidate.appendStream(message.part, message.values);
          } else if (message.kind === 'done') {
            if (!candidate || candidate.changes.length !== counts.changes || candidate.prices.length !== counts.prices
              || candidate.itemsById.size !== counts.items || candidate.evidenceById.size !== counts.evidence) {
              throw new DatasetError('incomplete dataset stream');
            }
            finish(); return;
          } else throw new DatasetError('unknown dataset stream message');
          worker.postMessage('ack');
        } catch (error) { finish(error as Error); }
      });
    });
  });
}
