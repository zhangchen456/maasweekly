/**
 * server.ts：agent-api 启动入口（Task 03 M5）。
 *
 * 默认绑定 127.0.0.1（生产由反向代理做 TLS）；PORT 环境变量定端口。
 * PUBLIC_DATA_ROOT 指定数据根（测试注入临时目录）；RELOAD_INTERVAL_MS
 * 轮询 manifest 热重载（0=禁用），另支持 SIGHUP。
 */
import http from 'node:http';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DatasetHolder } from './dataset.js';
import { createHandler, type ServerConfig } from './http.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..', '..');

const PORT = parseInt(process.env.PORT ?? '8787', 10);
const HOST = process.env.HOST ?? '127.0.0.1';
const DATA_ROOT = process.env.PUBLIC_DATA_ROOT
  ?? path.join(repoRoot, 'data', 'public', 'v1');
const RELOAD_MS = parseInt(process.env.RELOAD_INTERVAL_MS ?? '30000', 10);

const config: ServerConfig = {
  rateLimit: {
    capacity: parseInt(process.env.RATE_CAPACITY ?? '60', 10),
    refillPerMinute: parseInt(process.env.RATE_REFILL_PER_MIN ?? '30', 10),
  },
};

// cursor MAC 密钥（验收 P1-2）：默认进程内随机（重启后旧 cursor 全失效，
// 可接受——cursor 是短期分页令牌）；多实例部署设 CURSOR_SECRET 共享。
import { setCursorSecret } from './query.js';
setCursorSecret(process.env.CURSOR_SECRET ?? randomUUID());

const holder = new DatasetHolder(DATA_ROOT);
if (holder.reload()) {
  console.log(`[agent-api] 已加载数据版本 ${holder.current?.version}`);
} else {
  console.warn(`[agent-api] 无有效数据版本（${holder.lastReloadError}），数据路由将 503`);
}

const server = http.createServer(createHandler(holder, config));
server.listen(PORT, HOST, () => {
  console.log(`[agent-api] http://${HOST}:${PORT}/api/v1/ （数据根: ${DATA_ROOT}）`);
});

let timer: NodeJS.Timeout | undefined;
if (RELOAD_MS > 0) {
  timer = setInterval(() => {
    if (holder.reload()) {
      console.log(`[agent-api] 热重载 → ${holder.current?.version}`);
    }
  }, RELOAD_MS);
  timer.unref?.();
}

process.on('SIGHUP', () => {
  if (holder.reload()) {
    console.log(`[agent-api] SIGHUP 重载 → ${holder.current?.version}`);
  } else {
    console.warn(`[agent-api] SIGHUP 重载失败（继续服务旧版）: ${holder.lastReloadError}`);
  }
});

const shutdown = () => {
  console.log('[agent-api] 关闭');
  timer?.unref?.();
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 3000).unref?.();
};
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
