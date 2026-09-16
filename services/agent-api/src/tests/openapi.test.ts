/**
 * T17：OpenAPI 与真实路由对照（import routes 元数据 + openapi 文件）。
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ROUTES } from '../http.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const openapiPath = path.resolve(__dirname, '..', '..', '..', '..', 'site', 'public', 'openapi-v1.json');

test('T17 OpenAPI 路径与真实路由一致', () => {
  const spec = JSON.parse(readFileSync(openapiPath, 'utf-8')) as {
    paths: Record<string, { get?: { parameters?: { name: string; in: string }[]; responses: Record<string, unknown> } }>;
  };
  const specPaths = new Set(Object.keys(spec.paths));
  const implPaths = new Set(ROUTES.map((r) => r.path));
  assert.deepEqual([...specPaths].sort(), [...implPaths].sort(),
    '路径集合必须相等（无文档假接口、无未文档路由）');

  for (const route of ROUTES) {
    const op = spec.paths[route.path]?.get;
    assert.ok(op, `OpenAPI 缺 ${route.path}`);
    // 参数集合一致
    const specParams = (op.parameters ?? []).filter((p) => p.in === 'query').map((p) => p.name).sort();
    assert.deepEqual(specParams, [...route.params].sort(), `${route.path} 参数不一致`);
    // 状态码：文档 ⊆ 实现
    const specStatuses = new Set(Object.keys(op.responses ?? {}));
    for (const s of specStatuses) {
      assert.ok(route.statusCodes.includes(parseInt(s, 10)),
        `${route.path} 文档声明 ${s} 但实现元数据无此状态码`);
    }
    assert.ok(specStatuses.has('200'), `${route.path} 缺 200`);
  }
});
