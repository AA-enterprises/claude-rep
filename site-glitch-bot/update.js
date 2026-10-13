#!/usr/bin/env node
// Updates this folder to the latest version on GitHub: `node update.js`.
// Needs nothing but Node (no git). Your reports and node_modules are kept.
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const REPO = 'AA-enterprises/claude-rep';
const BRANCH = 'claude/epic-pasteur-f6hbt5';
const FOLDER = 'site-glitch-bot/';

const here = path.dirname(fileURLToPath(import.meta.url));
const versionFile = path.join(here, '.version');

async function getJson(url) {
  const res = await fetch(url, { headers: { 'User-Agent': 'site-glitch-bot-updater', Accept: 'application/vnd.github+json' } });
  if (res.status === 403 || res.status === 429) throw new Error('GitHub ne abhi rok diya (rate limit). 1 ghante baad dobara try karein.');
  if (!res.ok) throw new Error(`GitHub se jawab nahi mila (HTTP ${res.status}) for ${url}`);
  return res.json();
}

async function main() {
  console.log('Naya version check ho raha hai...');
  const commit = await getJson(`https://api.github.com/repos/${REPO}/commits/${BRANCH}`);
  const sha = commit.sha;
  const current = await fs.readFile(versionFile, 'utf8').catch(() => '');
  if (current.trim() === sha) {
    console.log('Bot pehle se latest version par hai. Kuch update nahi karna.');
    return;
  }

  const tree = await getJson(`https://api.github.com/repos/${REPO}/git/trees/${commit.commit.tree.sha}?recursive=1`);
  const files = tree.tree.filter((t) => t.type === 'blob' && t.path.startsWith(FOLDER));
  const changed = [];
  for (const f of files) {
    const rel = f.path.slice(FOLDER.length);
    // Raw URL pinned to the commit, so a cached old copy is never served.
    const res = await fetch(`https://raw.githubusercontent.com/${REPO}/${sha}/${f.path}`);
    if (!res.ok) throw new Error(`Download fail: ${rel} (HTTP ${res.status})`);
    let data = Buffer.from(await res.arrayBuffer());
    if (rel.endsWith('.cmd')) data = Buffer.from(data.toString('utf8').replace(/\r?\n/g, '\r\n'));
    const dest = path.join(here, ...rel.split('/'));
    const old = await fs.readFile(dest).catch(() => null);
    if (old && old.equals(data)) continue;
    await fs.mkdir(path.dirname(dest), { recursive: true });
    await fs.writeFile(dest, data);
    changed.push(rel);
  }

  const depsChanged = changed.some((f) => f === 'package.json' || f === 'package-lock.json');
  const hasDeps = await fs.access(path.join(here, 'node_modules', 'playwright')).then(() => true, () => false);
  if (depsChanged || !hasDeps) {
    console.log('Zaroori packages update ho rahe hain...');
    const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
    const r = spawnSync(npm, ['install', '--no-audit', '--no-fund'], { cwd: here, stdio: 'inherit', shell: process.platform === 'win32' });
    if (r.status !== 0) throw new Error('npm install fail ho gaya.');
    const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
    spawnSync(npx, ['playwright', 'install', 'chromium'], { cwd: here, stdio: 'inherit', shell: process.platform === 'win32' });
  }

  await fs.writeFile(versionFile, sha + '\n');
  console.log(changed.length
    ? `Update ho gaya! ${changed.length} file(s) badli: ${changed.join(', ')}`
    : 'Update ho gaya! (files pehle se naye thay)');
  console.log(`Version: ${sha.slice(0, 7)} — ${commit.commit.message.split('\n')[0]}`);
}

main().catch((e) => {
  console.error('Update nahi ho saka:', e.message);
  process.exit(1);
});
