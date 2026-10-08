import { contentSchema, type ProStore } from './pro-store.js';
import { validateEditorial } from './pro-editorial.js';
import type { Dataset } from './dataset.js';
/** Both CLI and workbench publish through this service; caller owns the short transaction. */
export function publishInTransaction(store: ProStore, id: string, version: number, actor: string, note: string, ds: Dataset) {
  const row=store.db.prepare('SELECT payload FROM pro_content WHERE id=? AND version=?').get(id,version);
  if (!row) throw new Error('draft not found');
  validateEditorial(contentSchema.parse(JSON.parse(String(row.payload))),ds);
  store.transitionInTransaction(id,version,'publish',actor,note);
}
