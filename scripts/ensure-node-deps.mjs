#!/usr/bin/env node
// Dependency cache is valid only for this lockfile, toolchain and platform.
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const root = path.resolve(process.argv[2] ?? '');
if (!process.argv[2]) throw new Error('Usage: ensure-node-deps.mjs <package-directory>');
const lock = fs.readFileSync(path.join(root, 'package-lock.json'));
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const key = JSON.stringify({ lock: createHash('sha256').update(lock).digest('hex'), node: process.version,
  abi: process.versions.modules, npm: execFileSync(npm, ['--version'], { encoding: 'utf8' }).trim(), platform: process.platform, arch: process.arch });
const marker = path.join(root, 'node_modules', '.maas-deps.json');
let cached;
try { cached = fs.readFileSync(marker, 'utf8'); } catch { /* first install */ }
if (cached === key && fs.existsSync(path.join(root, 'node_modules', '.bin', 'tsc'))) {
  console.log(`Dependency cache valid: ${path.basename(root)}`);
} else {
  execFileSync(npm, ['ci', '--prefer-offline', '--silent'], { cwd: root, stdio: 'inherit' });
  fs.writeFileSync(marker, key);
  console.log(`Dependency cache installed: ${path.basename(root)}`);
}
