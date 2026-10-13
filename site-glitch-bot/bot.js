#!/usr/bin/env node
// Site Glitch Bot: crawls a website you own in a real Chromium browser and
// reports everything that looks broken. See README.md for usage.
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { renderHtmlReport } from './report.js';
import * as deep from './deep.js';

const HELP = `
Site Glitch Bot - find glitches on your own websites

Usage:
  node bot.js <url> [options]

Deep scan is ON by default: scrolls every page, clicks safe buttons/menus/tabs
(never submit/buy/delete; form sends are blocked), measures speed and layout
shift, runs accessibility checks and whole-site security checks.

Options:
  --quick               Fast surface scan only (no clicking, no deep checks)
  --max-clicks <n>      Buttons to click per page in deep mode (default 25)
  --urls <file>         Text file with extra page URLs to check (one per line)
  --max-pages <n>       Pages to crawl (default 200)
  --concurrency <n>     Pages checked in parallel (default 4)
  --delay <ms>          Pause between page loads per worker (default 250)
  --timeout <ms>        Page load timeout (default 30000)
  --slow <ms>           Flag pages slower than this (default 4000)
  --check-external      Also check links that leave your site (HEAD request)
  --no-mobile           Skip the mobile-viewport layout check
  --no-sitemap          Don't seed the crawl from /sitemap.xml
  --ignore-robots       Crawl paths that robots.txt disallows
  --include <regex>     Only crawl URLs matching this pattern
  --exclude <regex>     Skip URLs matching this pattern (e.g. "logout|/cart")
  --out <dir>           Report folder (default ./glitch-report)
  --fail-on <level>     Exit with code 1 if issues at this level exist:
                        critical | warning | none (default critical)
  -h, --help            Show this help
`;

function parseArgs(argv) {
  const opts = {
    maxPages: 200, concurrency: 4, delay: 250, timeout: 30000, slow: 4000,
    checkExternal: false, mobile: true, sitemap: true, robots: true,
    include: null, exclude: null, out: 'glitch-report', failOn: 'critical',
    quick: false, maxClicks: 25, urls: null,
  };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => {
      const v = argv[++i];
      if (v === undefined) throw new Error(`${a} needs a value`);
      return v;
    };
    switch (a) {
      case '-h': case '--help': opts.help = true; break;
      case '--quick': opts.quick = true; break;
      case '--max-clicks': opts.maxClicks = +next(); break;
      case '--urls': opts.urls = next(); break;
      case '--max-pages': opts.maxPages = +next(); break;
      case '--concurrency': opts.concurrency = Math.max(1, +next()); break;
      case '--delay': opts.delay = +next(); break;
      case '--timeout': opts.timeout = +next(); break;
      case '--slow': opts.slow = +next(); break;
      case '--check-external': opts.checkExternal = true; break;
      case '--no-mobile': opts.mobile = false; break;
      case '--no-sitemap': opts.sitemap = false; break;
      case '--ignore-robots': opts.robots = false; break;
      case '--include': opts.include = new RegExp(next()); break;
      case '--exclude': opts.exclude = new RegExp(next()); break;
      case '--out': opts.out = next(); break;
      case '--fail-on': opts.failOn = next(); break;
      default:
        if (a.startsWith('-')) throw new Error(`Unknown option ${a}`);
        rest.push(a);
    }
  }
  opts.start = rest[0];
  return opts;
}

// ---------- URL helpers ----------

const SKIP_EXT = /\.(pdf|zip|rar|7z|gz|tar|exe|dmg|apk|mp4|mp3|wav|avi|mov|webm|jpg|jpeg|png|gif|webp|avif|svg|ico|woff2?|ttf|eot|css|js|json|xml|txt|csv|xlsx?|docx?|pptx?)$/i;

function normalize(raw, base) {
  try {
    const u = new URL(raw, base);
    if (!/^https?:$/.test(u.protocol)) return null;
    // Keep hash routes (#/about) used by single-page apps; drop plain #section.
    if (!/^#!?\//.test(u.hash)) u.hash = '';
    // Drop common tracking params so the same page isn't crawled many times.
    for (const k of [...u.searchParams.keys()]) {
      if (/^(utm_|fbclid$|gclid$|mc_)/i.test(k)) u.searchParams.delete(k);
    }
    return u.toString();
  } catch {
    return null;
  }
}

const sameSite = (a, b) => {
  const strip = (h) => h.replace(/^www\./, '');
  return strip(new URL(a).hostname) === strip(new URL(b).hostname);
};

// ---------- robots.txt / sitemap ----------

async function loadRobots(origin, request) {
  const rules = [];
  try {
    const res = await request.get(`${origin}/robots.txt`, { timeout: 10000 });
    if (!res.ok()) return rules;
    let applies = false;
    for (const line of (await res.text()).split(/\r?\n/)) {
      const [k, ...v] = line.split(':');
      const key = k.trim().toLowerCase();
      const val = v.join(':').trim();
      if (key === 'user-agent') applies = val === '*' || /glitch/i.test(val);
      else if (applies && (key === 'disallow' || key === 'allow') && val) {
        rules.push({ allow: key === 'allow', path: val });
      }
    }
  } catch { /* no robots.txt is fine */ }
  return rules;
}

function robotsAllows(rules, url) {
  const p = new URL(url).pathname + new URL(url).search;
  let best = null;
  for (const r of rules) {
    const pattern = new RegExp('^' + r.path.replace(/[.+?^${}()|[\]\\]/g, '\\$&')
      .replace(/\*/g, '.*').replace(/\\\$$/, '$'));
    if (pattern.test(p) && (!best || r.path.length > best.path.length)) best = r;
  }
  return !best || best.allow;
}

async function loadSitemap(url, request, seen = new Set()) {
  if (seen.has(url) || seen.size > 20) return [];
  seen.add(url);
  try {
    const res = await request.get(url, { timeout: 15000 });
    if (!res.ok()) return [];
    const xml = await res.text();
    const locs = [...xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/gi)].map((m) =>
      m[1].replace(/&amp;/g, '&'));
    if (/<sitemapindex/i.test(xml)) {
      const nested = await Promise.all(locs.map((l) => loadSitemap(l, request, seen)));
      return nested.flat();
    }
    return locs;
  } catch {
    return [];
  }
}

// ---------- In-page checks (run inside the browser) ----------

function inPageAudit() {
  const out = { links: [], issues: [] };
  const add = (severity, type, message, detail) =>
    out.issues.push({ severity, type, message, detail });

  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href').trim();
    if (!href || href === '#' || /^javascript:/i.test(href)) {
      if (!a.onclick && !a.getAttribute('role')) {
        add('info', 'dead-link', 'Link goes nowhere', `"${a.textContent.trim().slice(0, 60)}" href="${href}"`);
      }
      continue;
    }
    out.links.push({ href: a.href, text: a.textContent.trim().slice(0, 80) });
  }

  for (const img of document.querySelectorAll('img')) {
    const src = img.currentSrc || img.src;
    if (img.complete && img.naturalWidth === 0 && src && img.loading !== 'lazy') {
      add('critical', 'broken-image', 'Image failed to load', src);
    }
    if (!img.hasAttribute('alt')) add('info', 'img-no-alt', 'Image has no alt text', src);
  }

  const title = document.title.trim();
  out.title = title;
  if (!title) add('warning', 'seo', 'Page has no <title>');
  const desc = document.querySelector('meta[name="description"]');
  if (!desc || !desc.content.trim()) add('info', 'seo', 'Missing meta description');
  const h1s = document.querySelectorAll('h1').length;
  if (h1s === 0) add('info', 'seo', 'No <h1> heading on page');
  if (h1s > 1) add('info', 'seo', `${h1s} <h1> headings on page`);
  if (!document.querySelector('meta[name="viewport"]')) {
    add('warning', 'mobile', 'No viewport meta tag: page will look zoomed-out on phones');
  }
  if (!document.documentElement.lang) add('info', 'a11y', '<html> has no lang attribute');

  const ids = {};
  for (const el of document.querySelectorAll('[id]')) ids[el.id] = (ids[el.id] || 0) + 1;
  const dupes = Object.entries(ids).filter(([, n]) => n > 1).map(([id]) => id);
  if (dupes.length) add('info', 'html', 'Duplicate element ids', dupes.slice(0, 10).join(', '));

  for (const f of document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea')) {
    const labelled = f.id && document.querySelector(`label[for="${CSS.escape(f.id)}"]`);
    if (!labelled && !f.closest('label') && !f.getAttribute('aria-label') && !f.getAttribute('aria-labelledby') && !f.placeholder) {
      add('info', 'a11y-label', 'Form field has no label', f.outerHTML.slice(0, 100));
    }
  }

  const text = document.body ? document.body.innerText : '';
  if (text.trim().length < 20) add('warning', 'blank-page', 'Page looks blank (almost no visible text)');
  const leaks = [
    [/\bundefined\b|\bNaN\b|\[object Object\]/, 'Template/JS value leaked into page text'],
    [/\{\{\s*[\w.]+\s*\}\}/, 'Unrendered template tag ({{ }}) visible on page'],
    [/(Fatal error|Warning|Parse error|Notice):.*on line \d+/, 'PHP error printed on page'],
    [/Traceback \(most recent call last\)|Exception in thread|stack trace:/i, 'Server error trace visible on page'],
    [/lorem ipsum/i, 'Placeholder "lorem ipsum" text left on page'],
  ];
  for (const [re, msg] of leaks) {
    const m = text.match(re);
    if (m) {
      const i = Math.max(0, m.index - 40);
      add('warning', 'content', msg, '…' + text.slice(i, m.index + 60).replace(/\s+/g, ' ') + '…');
    }
  }
  return out;
}

function overflowAudit() {
  const vw = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth <= vw + 2) return null;
  const culprits = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.right > vw + 2 && getComputedStyle(el).position !== 'fixed') {
      const name = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
        (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '');
      culprits.push(`${name} (${Math.round(r.right - vw)}px too wide)`);
      if (culprits.length >= 5) break;
    }
  }
  return { pageWidth: document.documentElement.scrollWidth, viewport: vw, culprits };
}

// ---------- Page check ----------

async function checkPage(context, url, opts, origin, shared) {
  const page = await context.newPage();
  const issues = [];
  const add = (severity, type, message, detail) => issues.push({ severity, type, message, detail });
  const pageHttps = url.startsWith('https:');

  // While the bot is clicking, errors are labelled with what was clicked.
  let action = null;
  let blockedSince = () => false;
  const setAction = (a, blocked = () => false) => { action = a; blockedSince = blocked; };

  page.on('pageerror', (err) => {
    if (!action) return add('critical', 'js-error', 'Uncaught JavaScript error', err.message);
    // If the bot blocked a form send just before, the error may be the bot's doing.
    if (blockedSince()) return add('info', 'js-error', `JavaScript error ${action} (a send was blocked by the bot)`, err.message);
    add('critical', 'js-error', `JavaScript error ${action}`, err.message);
  });
  page.on('console', (msg) => {
    // Network failures are already reported by the response/requestfailed handlers.
    if (msg.type() === 'error' && !/^Failed to load resource/.test(msg.text())) {
      add(action && blockedSince() ? 'info' : 'warning', 'console-error', action ? `Console error ${action}` : 'Console error', msg.text().slice(0, 300));
    }
  });

  // Page weight and heavy files.
  let bytes = 0;
  const sizeJobs = [];
  page.on('requestfinished', (req) => sizeJobs.push(req.sizes().then((s) => {
    const n = s.responseBodySize;
    bytes += n;
    const type = req.resourceType();
    const mb = (n / 1048576).toFixed(1);
    if (type === 'image' && n > 400 * 1024) add('warning', 'heavy-file', `Heavy image (${mb} MB): compress it or use WebP`, req.url());
    else if ((type === 'script' || type === 'stylesheet') && n > 1024 * 1024) add('warning', 'heavy-file', `Heavy ${type} (${mb} MB)`, req.url());
    else if (type === 'media' && n > 8 * 1024 * 1024) add('info', 'heavy-file', `Large video/audio (${mb} MB)`, req.url());
  }).catch(() => {})));
  page.on('requestfailed', (req) => {
    const err = req.failure()?.errorText || '';
    if (/ERR_ABORTED|ERR_BLOCKED_BY_CLIENT/.test(err)) return;
    add(req.resourceType() === 'document' ? 'critical' : 'warning', 'request-failed',
      `${req.resourceType()} failed to load`, `${req.url()} (${err})`);
  });
  page.on('response', (res) => {
    const req = res.request();
    if (req.resourceType() === 'document' && req.frame() === page.mainFrame()) return;
    if (res.status() >= 400) {
      const firstParty = sameSite(res.url(), origin);
      add(firstParty ? 'critical' : 'warning', 'resource-error',
        `${req.resourceType()} returned HTTP ${res.status()}`, res.url());
    }
  });
  page.on('request', (req) => {
    if (pageHttps && req.url().startsWith('http:')) {
      add('warning', 'mixed-content', 'Insecure http:// resource on https page', req.url());
    }
  });

  const result = { url, status: null, finalUrl: url, loadMs: null, title: '', links: [], issues };
  const t0 = Date.now();
  try {
    const res = await page.goto(url, { waitUntil: 'load', timeout: opts.timeout });
    result.loadMs = Date.now() - t0;
    await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
    result.status = res ? res.status() : null;
    result.finalUrl = page.url();
    result.headers = res ? res.headers() : {};

    if (res) {
      const chain = [];
      for (let r = res.request().redirectedFrom(); r; r = r.redirectedFrom()) chain.push(r.url());
      if (chain.length > 1) add('warning', 'redirect', `Redirect chain of ${chain.length} hops`, [...chain.reverse(), result.finalUrl].join(' → '));
      if (result.status >= 500) add('critical', 'http-error', `Server error ${result.status}`);
      else if (result.status >= 400) add('critical', 'http-error', `Page returned ${result.status}`);
      const ct = res.headers()['content-type'] || '';
      // An error page or non-HTML file has nothing else worth auditing.
      if (result.status >= 400 || !ct.includes('html')) {
        await page.close();
        result.skipped = result.status >= 400 ? 'error page' : 'not html';
        return result;
      }
    }
    if (pageHttps && result.finalUrl.startsWith('http:')) {
      add('critical', 'security', 'https page redirects to insecure http', result.finalUrl);
    }
    if (result.loadMs > opts.slow) add('warning', 'slow', `Slow page: ${(result.loadMs / 1000).toFixed(1)}s to load`);

    // Soft 404: page says "not found" but server returned 200.
    if (result.status === 200) {
      const soft = await page.evaluate(() =>
        /\b(404|page not found|not found|doesn't exist|does not exist)\b/i.test(document.title));
      if (soft) add('warning', 'soft-404', 'Page looks like a "not found" page but returns HTTP 200');
    }

    const audit = await page.evaluate(inPageAudit);
    result.title = audit.title;
    result.links = audit.links;
    // A 404 image is already reported as a resource error; don't count it twice.
    const failedUrls = new Set(issues.map((i) => i.detail));
    issues.push(...audit.issues.filter((i) => !(i.type === 'broken-image' && failedUrls.has(i.detail))));

    if (!opts.quick) {
      const v = await page.evaluate(deep.readVitals);
      result.vitals = { lcp: v.lcp, cls: +v.cls.toFixed(3), blockingMs: v.blockingMs };
      if (v.lcp > 4000) add('warning', 'speed', `Main content shows after ${(v.lcp / 1000).toFixed(1)}s (Google wants under 2.5s)`, v.lcpEl && `Biggest element: ${v.lcpEl}`);
      else if (v.lcp > 2500) add('info', 'speed', `Main content shows after ${(v.lcp / 1000).toFixed(1)}s (Google wants under 2.5s)`, v.lcpEl && `Biggest element: ${v.lcpEl}`);
      if (v.cls > 0.25) add('warning', 'layout-shift', `Page jumps around while loading (layout shift ${v.cls.toFixed(2)}, should be under 0.1)`, v.shifters.join('; '));
      else if (v.cls > 0.1) add('info', 'layout-shift', `Some jumping while loading (layout shift ${v.cls.toFixed(2)})`, v.shifters.join('; '));
      if (v.blockingMs > 600) add('warning', 'speed', `Page freezes for ${v.blockingMs}ms while JavaScript runs (buttons won't respond)`);

      await deep.scrollThrough(page);
      const d = await page.evaluate(deep.deepAudit);
      const seen = new Set(issues.map((i) => i.detail));
      issues.push(...d.issues.filter((i) => !(i.type === 'broken-image' && seen.has(i.detail))));
      if (d.canonical) {
        result.canonical = d.canonical;
        if (!sameSite(d.canonical, origin)) add('warning', 'seo', 'Canonical tag points to another website', d.canonical);
      }

      try {
        const violations = await deep.axeAudit(page);
        // axe covers these more accurately than the quick checks.
        for (let i = issues.length - 1; i >= 0; i--) if (['img-no-alt', 'a11y-label'].includes(issues[i].type)) issues.splice(i, 1);
        for (const v of violations) add('warning', 'a11y', `Accessibility: ${v.help}`, `${v.count} element(s), e.g. ${v.sample}`);
      } catch { /* axe is best-effort */ }
    }

    if (opts.mobile) {
      for (const [w, h, label] of opts.quick ? [[375, 812, 'mobile']] : [[375, 812, 'mobile'], [768, 1024, 'tablet']]) {
        await page.setViewportSize({ width: w, height: h });
        await page.waitForTimeout(400);
        const ov = await page.evaluate(overflowAudit);
        if (ov) {
          add('warning', 'layout', `Page scrolls sideways on ${label} (${ov.pageWidth}px wide on a ${ov.viewport}px screen)`,
            ov.culprits.join('; '));
        }
        if (!opts.quick && label === 'mobile') {
          const m = await page.evaluate(deep.mobileAudit);
          if (m.clipped.length) add('warning', 'layout', 'Text is cut off on mobile', m.clipped.join('; '));
          if (m.small.length > 3) add('info', 'mobile', `${m.small.length} buttons/links are too small to tap on a phone (under 24px)`, m.small.slice(0, 5).join('; '));
        }
      }
      await page.setViewportSize({ width: 1366, height: 900 });
    }

    if (!opts.quick && opts.maxClicks > 0) {
      result.clicks = await deep.interact(page, result.finalUrl, opts, {
        clicked: shared.clicked, onNewUrl: shared.onNewUrl, setAction, add, issues,
      });
    }
  } catch (err) {
    result.loadMs = Date.now() - t0;
    add('critical', 'load-failed', 'Page could not be loaded', err.message.split('\n')[0]);
  }

  if (issues.some((i) => i.severity === 'critical')) {
    try {
      await page.setViewportSize({ width: 1366, height: 900 });
      // Hex hash: safe on Windows, where file names are case-insensitive.
      const file = `shot-${crypto.createHash('sha1').update(url).digest('hex').slice(0, 16)}.png`;
      await page.screenshot({ path: path.join(opts.out, file), timeout: 10000 });
      result.screenshot = file;
    } catch { /* screenshot is best-effort */ }
  }
  await Promise.allSettled(sizeJobs);
  result.bytes = bytes;
  if (!opts.quick && bytes > 5 * 1048576) add('warning', 'heavy-page', `Page downloads ${(bytes / 1048576).toFixed(1)} MB (slow on mobile data)`);
  await page.close();
  return result;
}

// ---------- Crawl ----------

async function crawl(opts) {
  const start = normalize(opts.start);
  if (!start) throw new Error(`Not a valid http(s) URL: ${opts.start}`);
  const origin = new URL(start).origin;
  await fs.mkdir(opts.out, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (compatible; SiteGlitchBot/1.0; site-owner audit) Chrome/141 Safari/537.36',
    ignoreHTTPSErrors: false,
    viewport: { width: 1366, height: 900 },
  });
  if (!opts.quick) await context.addInitScript(deep.initScript);
  const request = context.request;

  const robots = opts.robots ? await loadRobots(origin, request) : [];
  const queue = [start];
  const queued = new Set([start]);
  const referrers = new Map(); // url -> [{from, text}]
  const results = [];
  const external = new Map(); // url -> [{from, text}]
  const skipped = { robots: 0, filtered: 0 };

  const enqueue = (url) => {
    if (queued.has(url) || queued.size >= opts.maxPages) return;
    if (opts.include && !opts.include.test(url)) { skipped.filtered++; return; }
    if (opts.exclude && opts.exclude.test(url)) { skipped.filtered++; return; }
    if (!robotsAllows(robots, url)) { skipped.robots++; return; }
    queued.add(url);
    queue.push(url);
  };

  if (opts.urls) {
    const lines = (await fs.readFile(opts.urls, 'utf8')).split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    for (const l of lines) {
      const n = normalize(l, origin);
      if (n && sameSite(n, origin)) enqueue(n);
    }
    log(`Added ${lines.length} URLs from ${opts.urls}`);
  }

  // Shared across pages: header/footer buttons get clicked once, not on every page.
  const clicked = new Set();
  const discovered = new Set();
  const onNewUrl = (raw) => {
    const n = normalize(raw);
    if (!n || !sameSite(n, origin) || SKIP_EXT.test(new URL(n).pathname)) return;
    if (!queued.has(n)) discovered.add(n);
    enqueue(n);
  };

  if (opts.sitemap) {
    const urls = await loadSitemap(`${origin}/sitemap.xml`, request);
    for (const u of urls) {
      const n = normalize(u);
      if (n && sameSite(n, origin)) enqueue(n);
    }
    if (urls.length) log(`Seeded ${urls.length} URLs from sitemap.xml`);
  }

  let done = 0;
  let inFlight = 0;
  async function worker() {
    for (;;) {
      if (!queue.length) {
        // Another worker may still find new links; wait for it before quitting.
        if (inFlight === 0) return;
        await new Promise((res) => setTimeout(res, 100));
        continue;
      }
      const url = queue.shift();
      inFlight++;
      try {
        const r = await checkPage(context, url, opts, origin, { clicked, onNewUrl });
        results.push(r);
        done++;
        const crit = r.issues.filter((i) => i.severity === 'critical').length;
        log(`[${done}/${queued.size}] ${r.status ?? 'ERR'} ${url}${crit ? `  ⚠ ${crit} critical` : ''}${r.clicks ? `  (${r.clicks} clicks)` : ''}`);
        if (r.canonical) onNewUrl(r.canonical);
        for (const l of r.links) {
          const n = normalize(l.href, r.finalUrl);
          if (!n) continue;
          const ref = { from: url, text: l.text };
          if (sameSite(n, origin)) {
            if (!referrers.has(n)) referrers.set(n, []);
            referrers.get(n).push(ref);
            if (!SKIP_EXT.test(new URL(n).pathname)) enqueue(n);
          } else if (opts.checkExternal) {
            if (!external.has(n)) external.set(n, []);
            external.get(n).push(ref);
          }
        }
      } finally {
        inFlight--;
      }
      if (opts.delay) await new Promise((res) => setTimeout(res, opts.delay));
    }
  }
  await Promise.all(Array.from({ length: opts.concurrency }, worker));
  if (discovered.size) log(`Found ${discovered.size} extra pages by clicking buttons/menus`);

  let siteIssues = [];
  const home = results.find((r) => r.url === start) || results[0];
  if (!opts.quick && home?.status) {
    log('Running whole-site checks (SSL, security headers, exposed files)…');
    siteIssues = await deep.siteChecks(start, request, home?.headers);
  }
  for (const r of results) delete r.headers;

  // Attach "linked from" info to broken pages.
  for (const r of results) {
    const refs = referrers.get(r.url);
    if (refs && r.issues.some((i) => i.type === 'http-error' || i.type === 'load-failed')) {
      r.linkedFrom = refs.slice(0, 10);
    }
  }

  // Internal non-HTML files (PDFs, images) linked from pages: check they exist.
  const fileLinks = [...referrers.keys()].filter((u) => SKIP_EXT.test(new URL(u).pathname));
  const brokenFiles = await checkUrls(fileLinks, request, referrers, opts);

  let brokenExternal = [];
  if (opts.checkExternal) {
    log(`Checking ${external.size} external links…`);
    brokenExternal = await checkUrls([...external.keys()], request, external, opts);
  }

  // Duplicate titles across the site.
  const byTitle = new Map();
  for (const r of results) {
    if (!r.title || r.skipped) continue;
    if (!byTitle.has(r.title)) byTitle.set(r.title, []);
    byTitle.get(r.title).push(r.url);
  }
  const duplicateTitles = [...byTitle].filter(([, urls]) => urls.length > 1)
    .map(([title, urls]) => ({ title, urls }));

  await browser.close();
  return { start, startedAt: new Date().toISOString(), opts, results, brokenFiles, brokenExternal, duplicateTitles, skipped,
    siteIssues, discovered: [...discovered] };
}

async function checkUrls(urls, request, refMap, opts) {
  const broken = [];
  const list = [...urls];
  async function w() {
    while (list.length) {
      const u = list.shift();
      let status = null, error = null;
      try {
        let res = await request.head(u, { timeout: 15000, maxRedirects: 5 });
        // Many servers reject HEAD; retry with GET before calling it broken.
        if (res.status() >= 400) res = await request.get(u, { timeout: 15000, maxRedirects: 5 });
        status = res.status();
      } catch (e) {
        error = e.message.split('\n')[0];
      }
      if (error || status >= 400) {
        broken.push({ url: u, status, error, linkedFrom: (refMap.get(u) || []).slice(0, 10) });
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(8, opts.concurrency * 2) }, w));
  return broken;
}

function log(msg) {
  process.stderr.write(msg + '\n');
}

function summarize(report) {
  const counts = { critical: 0, warning: 0, info: 0 };
  for (const r of report.results) for (const i of r.issues) counts[i.severity]++;
  for (const i of report.siteIssues) counts[i.severity]++;
  counts.critical += report.brokenFiles.length;
  counts.warning += report.brokenExternal.length + report.duplicateTitles.length;
  return counts;
}

// Short list of the worst problems right in the terminal.
function printTop(report) {
  const groups = new Map();
  const addIssue = (i, where) => {
    if (i.severity === 'info') return;
    const key = `${i.severity}|${i.message}`;
    if (!groups.has(key)) groups.set(key, { ...i, pages: new Set() });
    groups.get(key).pages.add(where);
  };
  for (const i of report.siteIssues) addIssue(i, 'whole site');
  for (const r of report.results) for (const i of r.issues) addIssue(i, r.url);
  for (const b of report.brokenFiles) addIssue({ severity: 'critical', message: 'Broken link to a file', detail: b.url }, b.url);
  const top = [...groups.values()].sort((a, b) => (a.severity === b.severity ? b.pages.size - a.pages.size : a.severity === 'critical' ? -1 : 1));
  if (!top.length) return;
  console.log('\n  Top problems:');
  for (const g of top.slice(0, 15)) {
    const where = g.pages.size > 1 ? `${g.pages.size} pages` : [...g.pages][0];
    console.log(`  ${g.severity === 'critical' ? '[CRITICAL]' : '[warning] '} ${g.message}  — ${where}`);
    if (g.detail) console.log(`             ${String(g.detail).slice(0, 110)}`);
  }
  if (top.length > 15) console.log(`  …and ${top.length - 15} more in the report`);
  console.log('');
}

async function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (e) {
    console.error(e.message + '\n' + HELP);
    process.exit(2);
  }
  if (opts.help || !opts.start) {
    console.log(HELP);
    process.exit(opts.help ? 0 : 2);
  }
  if (!/^https?:\/\//.test(opts.start)) opts.start = 'https://' + opts.start;

  log(`Scanning ${opts.start} (up to ${opts.maxPages} pages)…`);
  const report = await crawl(opts);
  report.counts = summarize(report);

  const jsonOpts = { ...report.opts, include: String(report.opts.include), exclude: String(report.opts.exclude) };
  await fs.writeFile(path.join(opts.out, 'report.json'), JSON.stringify({ ...report, opts: jsonOpts }, null, 2));
  await fs.writeFile(path.join(opts.out, 'report.html'), renderHtmlReport(report));

  const c = report.counts;
  console.log(`\nDone: ${report.results.length} pages scanned.`);
  console.log(`  Critical: ${c.critical}   Warnings: ${c.warning}   Info: ${c.info}`);
  printTop(report);
  console.log(`  Report: ${path.resolve(opts.out, 'report.html')}`);

  const fail = opts.failOn === 'critical' ? c.critical > 0
    : opts.failOn === 'warning' ? c.critical + c.warning > 0 : false;
  process.exit(fail ? 1 : 0);
}

main().catch((e) => {
  console.error('Bot crashed:', e);
  process.exit(3);
});
