// Serves a small site with planted glitches, runs the bot on it and checks
// that each glitch shows up in report.json.
import http from 'node:http';
import { execFile } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const page = (title, body, head = '') => `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="x">
<title>${title}</title>${head}</head><body><h1>${title}</h1>${body}</body></html>`;

const routes = {
  '/': page('Home', `<p>Welcome to the test shop, this is the home page.</p>
    <a href="/about">About</a> <a href="/missing">Old link</a> <a href="/js-broken">Deals</a>
    <a href="/wide">Gallery</a> <a href="/crash">Checkout</a> <a href="/leak">Product</a>
    <a href="/files/menu.pdf">Menu PDF</a> <a href="/private/x">Admin</a>`),
  '/about': page('About', '<p>About us text that is long enough to count.</p><img src="/img/logo-gone.png" alt="logo">'),
  '/js-broken': page('Deals', '<p>Great deals today on everything we sell.</p><script>window.cart.total()</script>'),
  '/wide': page('Gallery', '<p>Our gallery of products and photos here.</p><div class="banner" style="width:1200px;height:20px"></div>'),
  '/leak': page('Product', '<p>Price: PKR undefined — order now while stocks last.</p>'),
  '/private/x': page('Secret', '<p>Should be skipped because of robots.txt rules.</p>'),
};

const server = http.createServer((req, res) => {
  if (req.url === '/robots.txt') return res.end('User-agent: *\nDisallow: /private/\n');
  if (req.url === '/crash') { res.writeHead(500, { 'content-type': 'text/html' }); return res.end('<h1>Internal error</h1>'); }
  const body = routes[req.url];
  if (!body) { res.writeHead(404, { 'content-type': 'text/html' }); return res.end('<h1>Not found</h1>'); }
  res.writeHead(200, { 'content-type': 'text/html' });
  res.end(body);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
const out = path.join(here, '.out');

const code = await new Promise((resolve) => {
  execFile('node', [path.join(here, '..', 'bot.js'), base + '/', '--out', out, '--delay', '0', '--no-sitemap'],
    (err, stdout, stderr) => { process.stdout.write(stderr + stdout); resolve(err ? err.code : 0); });
});
server.close();

const report = JSON.parse(await fs.readFile(path.join(out, 'report.json'), 'utf8'));
const issuesOf = (p) => report.results.find((r) => r.url === base + p)?.issues ?? [];
const has = (p, type) => issuesOf(p).some((i) => i.type === type);

const checks = [
  ['404 page found', has('/missing', 'http-error')],
  ['500 page found', has('/crash', 'http-error')],
  ['JS error found', has('/js-broken', 'js-error')],
  ['broken image found', has('/about', 'resource-error') || has('/about', 'broken-image')],
  ['mobile overflow found', has('/wide', 'layout')],
  ['"undefined" text leak found', has('/leak', 'content')],
  ['broken PDF link found', report.brokenFiles.some((b) => b.url.endsWith('/files/menu.pdf'))],
  ['robots.txt respected', !report.results.some((r) => r.url.includes('/private/'))],
  ['404 shows where it is linked from', report.results.find((r) => r.url === base + '/missing')?.linkedFrom?.length > 0],
  ['clean page has no critical issues', !issuesOf('/').some((i) => i.severity === 'critical')],
  ['exit code 1 on critical issues', code === 1],
];
let failed = 0;
for (const [name, ok] of checks) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`);
  if (!ok) failed++;
}
process.exit(failed ? 1 : 0);
