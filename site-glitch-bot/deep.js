// Deep-scan checks: things that only show up when you scroll, click, measure
// or look at the site as a whole. Used by bot.js unless --quick is passed.
import fs from 'node:fs/promises';
import tls from 'node:tls';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

// Clicking anything matching this could change data or cost money, so the
// bot never touches it.
export const RISKY_CLICK = 'delete|remove|log ?out|sign ?out|pay|checkout|place order|order now|buy|purchase|' +
  'subscribe|submit|send|confirm|cancel|book now|donate|deactivate|reset|clear|empty|whatsapp|tel:|mailto:|' +
  'add to cart|add to bag|wishlist|apply|register|sign ?up';

// ---------- Run inside the page ----------

// Installed before any page script runs, so long tasks during load are counted.
export function initScript() {
  window.__glitchLongTaskMs = 0;
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) window.__glitchLongTaskMs += Math.max(0, e.duration - 50);
    }).observe({ type: 'longtask', buffered: true });
  } catch { /* not supported */ }
}

export function readVitals() {
  const describe = (el) => {
    if (!el || !el.tagName) return '';
    const cls = typeof el.className === 'string' && el.className.trim()
      ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls;
  };
  return new Promise((resolve) => {
    const out = { cls: 0, lcp: null, lcpEl: '', shifters: [], blockingMs: Math.round(window.__glitchLongTaskMs || 0) };
    try {
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          if (e.hadRecentInput) continue;
          out.cls += e.value;
          for (const s of e.sources || []) {
            const d = describe(s.node);
            if (d && !out.shifters.includes(d) && out.shifters.length < 5) out.shifters.push(d);
          }
        }
      }).observe({ type: 'layout-shift', buffered: true });
    } catch { /* not supported */ }
    try {
      new PerformanceObserver((list) => {
        const all = list.getEntries();
        const last = all[all.length - 1];
        if (last) { out.lcp = Math.round(last.startTime); out.lcpEl = describe(last.element); }
      }).observe({ type: 'largest-contentful-paint', buffered: true });
    } catch { /* not supported */ }
    setTimeout(() => resolve(out), 400);
  });
}

export async function scrollThrough(page) {
  await page.evaluate(async () => {
    const step = Math.max(300, window.innerHeight * 0.8);
    for (let y = 0, i = 0; y < document.documentElement.scrollHeight && i < 60; y += step, i++) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, document.documentElement.scrollHeight);
    await new Promise((r) => setTimeout(r, 400));
    window.scrollTo(0, 0);
  });
  await page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => {});
}

// Checks that need the whole page loaded (after scrolling, so lazy content is in).
export function deepAudit() {
  const issues = [];
  const add = (severity, type, message, detail) => issues.push({ severity, type, message, detail });

  for (const img of document.querySelectorAll('img')) {
    const src = img.currentSrc || img.src;
    if (!src) continue;
    if (img.complete && img.naturalWidth === 0) add('critical', 'broken-image', 'Image failed to load', src);
    const shown = img.getBoundingClientRect().width;
    if (img.naturalWidth > 1000 && shown > 0 && img.naturalWidth > shown * 2.5) {
      add('info', 'oversized-image', `Image is ${img.naturalWidth}px wide but shown at ${Math.round(shown)}px (slows the page)`, src);
    }
  }

  for (const a of document.querySelectorAll('a[href^="#"]')) {
    const h = a.getAttribute('href').slice(1);
    if (!h || h.startsWith('/') || h.startsWith('!')) continue;
    let id = h;
    try { id = decodeURIComponent(h); } catch { /* keep raw */ }
    if (!document.getElementById(id) && !document.getElementsByName(id).length) {
      add('warning', 'broken-anchor', 'Link jumps to a section that does not exist',
        `"${a.textContent.trim().slice(0, 50)}" → #${h}`);
    }
  }

  const robots = document.querySelector('meta[name="robots"]')?.content || '';
  if (/noindex/i.test(robots)) add('warning', 'seo', 'Page is hidden from Google (meta robots noindex)');
  if (document.title.length > 65) add('info', 'seo', `Title is ${document.title.length} characters; Google cuts it after ~60`);
  if (!document.querySelector('meta[property="og:title"]')) add('info', 'seo', 'No og:title (link previews on WhatsApp/Facebook will look plain)');
  if (!document.querySelector('meta[property="og:image"]')) add('info', 'seo', 'No og:image (no picture when the link is shared)');

  const jq = window.jQuery?.fn?.jquery;
  if (jq) {
    const [maj, min] = jq.split('.').map(Number);
    if (maj < 3 || (maj === 3 && min < 5)) {
      add('warning', 'outdated-lib', `Old jQuery ${jq} with known security holes (update to 3.7+)`);
    }
  }

  const canonical = document.querySelector('link[rel="canonical"]')?.href || null;
  return { issues, canonical };
}

// Mobile-only checks: text cut off and buttons too small to tap.
export function mobileAudit() {
  const name = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
    (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const clipped = [];
  const small = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const cs = getComputedStyle(el);
    if (clipped.length < 5 && el.children.length === 0 && el.textContent.trim().length > 3 &&
        el.scrollWidth > el.clientWidth + 2 && /hidden|clip/.test(cs.overflowX) && cs.textOverflow !== 'ellipsis') {
      clipped.push(`${name(el)} "${el.textContent.trim().slice(0, 40)}"`);
    }
    if (el.matches('a[href], button, [role=button], input[type=checkbox], input[type=radio]') &&
        (r.width < 24 || r.height < 24) && !el.closest('p, li > p') && cs.display !== 'inline') {
      small.push(`${name(el)} ${Math.round(r.width)}×${Math.round(r.height)}px`);
    }
  }
  return { clipped, small };
}

export function tagClickables(risky) {
  const re = new RegExp(risky, 'i');
  const sel = 'button, [role=button], [role=tab], [role=menuitem], summary, [aria-expanded], [aria-haspopup], ' +
    '[onclick], a:not([href]), a[href^="#"]';
  for (const el of document.querySelectorAll('[data-glitch-click]')) el.removeAttribute('data-glitch-click');
  const out = [];
  let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    if (el.closest('form') && !el.matches('[role=tab], [aria-expanded]')) continue;
    if (el.matches('[type=submit], [disabled], [aria-disabled=true]')) continue;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width < 4 || r.height < 4 || cs.visibility === 'hidden' || cs.pointerEvents === 'none') continue;
    const text = (el.innerText || el.getAttribute('aria-label') || el.title || '').trim().replace(/\s+/g, ' ').slice(0, 60);
    if (re.test(text) || re.test(el.getAttribute('href') || '') || re.test(el.getAttribute('aria-label') || '')) continue;
    const id = 'g' + n++;
    el.setAttribute('data-glitch-click', id);
    out.push({ id, label: text || el.getAttribute('aria-label') || el.tagName.toLowerCase(),
      sig: el.tagName + '|' + text + '|' + (el.getAttribute('aria-controls') || '') + '|' + (el.getAttribute('href') || '') });
  }
  return out;
}

// ---------- Run in Node ----------

let axeSource;
export async function axeAudit(page) {
  axeSource ??= await fs.readFile(require.resolve('axe-core/axe.min.js'), 'utf8');
  // evaluate() runs outside the page's Content-Security-Policy, unlike a <script> tag.
  await page.evaluate(axeSource);
  return page.evaluate(async () => {
    const r = await window.axe.run(document, {
      resultTypes: ['violations'],
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
    });
    return r.violations
      .filter((v) => v.impact === 'critical' || v.impact === 'serious')
      .map((v) => ({ id: v.id, help: v.help, count: v.nodes.length,
        sample: v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(', ') }));
  });
}

// Clicks every safe button/tab/menu on the page and watches what breaks.
// Non-GET requests are blocked meanwhile, so nothing is ever saved or sent.
export async function interact(page, url, opts, state) {
  const { clicked, onNewUrl, setAction, add, issues } = state;
  let blocked = 0;
  await page.route('**/*', (route) => {
    if (route.request().method() !== 'GET') { blocked++; return route.abort('blockedbyclient'); }
    return route.fallback();
  });
  page.on('dialog', (d) => d.dismiss().catch(() => {}));
  page.on('popup', (p) => {
    p.waitForLoadState('domcontentloaded', { timeout: 5000 }).catch(() => {})
      .then(() => { onNewUrl(p.url()); return p.close(); }).catch(() => {});
  });
  page.on('download', (d) => d.cancel().catch(() => {}));

  let clicks = 0;
  let navigations = 0;
  while (clicks < opts.maxClicks) {
    const list = await page.evaluate(tagClickables, RISKY_CLICK).catch(() => []);
    const next = list.find((c) => !clicked.has(c.sig));
    if (!next) break;
    clicked.add(next.sig);
    clicks++;
    const before = blocked;
    const mark = issues.length;
    setAction(`after clicking "${next.label}"`, () => blocked > before);
    try {
      await page.locator(`[data-glitch-click="${next.id}"]`).click({ timeout: 2000 });
      await page.waitForTimeout(500);
    } catch {
      continue; // covered or moved: not a glitch by itself
    } finally {
      setAction(null);
    }
    const now = page.url();
    if (now.split('#')[0] !== url.split('#')[0] || /#!?\//.test(now) !== /#!?\//.test(url)) {
      // Errors from the page we landed on (and from reloading this one) are
      // not this page's problems; the new page gets its own full scan.
      issues.length = mark;
      onNewUrl(now);
      if (++navigations > 15) break;
      try {
        await page.goto(url, { waitUntil: 'load', timeout: opts.timeout });
      } catch {
        add('warning', 'interaction', 'Could not come back to the page after a click', next.label);
        break;
      }
      issues.length = mark;
    }
  }
  await page.unroute('**/*').catch(() => {});
  return clicks;
}

const EXPOSED = [
  ['/.env', (t, ct) => !/html/.test(ct) && /^[A-Z0-9_]+=/m.test(t), 'Secret .env file is public (passwords/API keys)'],
  ['/.git/config', (t) => /\[core\]/.test(t), 'Git folder is public (whole source code can be downloaded)'],
  ['/.git/HEAD', (t) => /^ref: refs\//.test(t), 'Git folder is public (whole source code can be downloaded)'],
  ['/wp-config.php.bak', (t) => /DB_PASSWORD/.test(t), 'WordPress config backup is public (database password)'],
  ['/phpinfo.php', (t) => /phpinfo\(\)|PHP Version/.test(t), 'phpinfo() page is public (server details)'],
  ['/info.php', (t) => /phpinfo\(\)|PHP Version/.test(t), 'phpinfo() page is public (server details)'],
  ['/server-status', (t) => /Apache Server Status/.test(t), 'Apache server-status page is public'],
  ['/database.sql', (t, ct) => !/html/.test(ct) && /CREATE TABLE|INSERT INTO/i.test(t), 'Database dump is public'],
  ['/backup.sql', (t, ct) => !/html/.test(ct) && /CREATE TABLE|INSERT INTO/i.test(t), 'Database dump is public'],
  ['/.DS_Store', (t) => t.includes('Bud1'), '.DS_Store file is public (lists hidden files)'],
  ['/uploads/', (t) => /<title>Index of \//i.test(t), 'Folder listing is open (anyone can browse files)'],
  ['/wp-content/uploads/', (t) => /<title>Index of \//i.test(t), 'Folder listing is open (anyone can browse files)'],
];

function certInfo(host) {
  return new Promise((resolve) => {
    const s = tls.connect({ host, port: 443, servername: host, rejectUnauthorized: false, timeout: 10000 }, () => {
      const c = s.getPeerCertificate();
      resolve({ authorized: s.authorized, error: s.authorizationError, validTo: c?.valid_to ? new Date(c.valid_to) : null });
      s.end();
    });
    s.on('error', () => resolve(null));
    s.on('timeout', () => { s.destroy(); resolve(null); });
  });
}

// Whole-site checks, run once: SSL, https redirect, security headers, exposed files.
export async function siteChecks(start, request, mainHeaders) {
  const issues = [];
  const add = (severity, type, message, detail) => issues.push({ severity, type, message, detail });
  const u = new URL(start);

  if (u.protocol === 'https:') {
    const cert = await certInfo(u.hostname);
    if (cert && !cert.authorized) add('critical', 'ssl', 'SSL certificate problem: browsers will show a warning', String(cert.error));
    if (cert?.validTo) {
      const days = Math.floor((cert.validTo - Date.now()) / 86400000);
      if (days < 0) add('critical', 'ssl', 'SSL certificate has EXPIRED');
      else if (days < 15) add('warning', 'ssl', `SSL certificate expires in ${days} days`, cert.validTo.toDateString());
    }
    try {
      const res = await request.get(`http://${u.host}/`, { maxRedirects: 0, timeout: 10000 });
      const loc = res.headers().location || '';
      if (res.status() < 300 && res.status() >= 200) add('warning', 'security', 'http:// version of the site does not redirect to https://');
      else if (res.status() >= 300 && res.status() < 400 && !loc.startsWith('https:')) {
        add('warning', 'security', 'http:// redirects somewhere that is not https', loc);
      }
    } catch { /* port 80 closed is fine */ }
  }

  const h = mainHeaders || {};
  if (u.protocol === 'https:' && !h['strict-transport-security']) add('info', 'security', 'Missing Strict-Transport-Security header');
  if (!h['x-content-type-options']) add('info', 'security', 'Missing X-Content-Type-Options header');
  if (!h['x-frame-options'] && !/frame-ancestors/.test(h['content-security-policy'] || '')) {
    add('info', 'security', 'Site can be embedded in other sites (clickjacking): add X-Frame-Options');
  }
  for (const k of ['server', 'x-powered-by']) {
    if (h[k] && /\d/.test(h[k])) add('warning', 'security', `Server reveals software version in "${k}" header`, h[k]);
  }

  for (const [p, test, msg] of EXPOSED) {
    try {
      const res = await request.get(new URL(p, start).toString(), { maxRedirects: 0, timeout: 10000 });
      if (res.status() !== 200) continue;
      const text = (await res.body()).toString('latin1').slice(0, 20000);
      if (test(text, res.headers()['content-type'] || '')) add('critical', 'exposed-file', msg, new URL(p, start).toString());
    } catch { /* unreachable is fine */ }
  }

  for (const [p, msg] of [['/robots.txt', 'No robots.txt file'], ['/sitemap.xml', 'No sitemap.xml (Google finds pages slower)']]) {
    try {
      const res = await request.get(new URL(p, start).toString(), { timeout: 10000 });
      const ct = res.headers()['content-type'] || '';
      if (!res.ok() || /html/.test(ct)) add('info', 'seo', msg);
    } catch { /* ignore */ }
  }
  return issues;
}
