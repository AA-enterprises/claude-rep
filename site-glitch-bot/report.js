// Builds a single self-contained HTML report from the crawl results.

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const SEV_ORDER = { critical: 0, warning: 1, info: 2 };

export function renderHtmlReport(report) {
  const c = report.counts;
  const pages = [...report.results]
    .filter((r) => r.issues.length)
    .sort((a, b) => worst(a) - worst(b) || b.issues.length - a.issues.length);

  // Group identical issues across the site so one broken footer image
  // doesn't show up as 200 separate problems.
  const groups = new Map();
  for (const i of report.siteIssues || []) {
    const key = `${i.severity}|${i.type}|${i.message}|${i.detail ?? ''}`;
    groups.set(key, { ...i, pages: ['(whole site)'] });
  }
  for (const r of report.results) {
    for (const i of r.issues) {
      const key = `${i.severity}|${i.type}|${i.message}|${i.detail ?? ''}`;
      if (!groups.has(key)) groups.set(key, { ...i, pages: [] });
      groups.get(key).pages.push(r.url);
    }
  }
  const topIssues = [...groups.values()]
    .sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity] || b.pages.length - a.pages.length);

  const slowest = [...report.results].filter((r) => r.loadMs).sort((a, b) => b.loadMs - a.loadMs).slice(0, 10);

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Glitch Report</title>
<style>
:root{--bg:#f7f7f8;--card:#fff;--text:#1a1a1f;--muted:#666a73;--line:#e3e4e8;
--crit:#c62828;--crit-bg:#fdecea;--warn:#a15c00;--warn-bg:#fff4e0;--info:#2457a6;--info-bg:#e8f0fc;--ok:#1b7f3b}
@media (prefers-color-scheme:dark){:root{--bg:#121316;--card:#1b1d22;--text:#ececf0;--muted:#9a9ea8;--line:#2c2f36;
--crit:#ff6b6b;--crit-bg:#3a1c1c;--warn:#f0b354;--warn-bg:#3a2c14;--info:#7fb0ff;--info-bg:#18263d;--ok:#5fd38a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{margin:0 0 4px;font-size:26px}h2{margin:36px 0 12px;font-size:19px}
.muted{color:var(--muted)}a{color:var(--info);word-break:break-all}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.stat b{display:block;font-size:28px}.stat.s-crit b{color:var(--crit)}.stat.s-warn b{color:var(--warn)}.stat.s-info b{color:var(--info)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
.pill{display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:99px;margin-right:6px;text-transform:uppercase;letter-spacing:.03em}
.critical{color:var(--crit);background:var(--crit-bg)}.warning{color:var(--warn);background:var(--warn-bg)}.info{color:var(--info);background:var(--info-bg)}
.detail{font:13px/1.4 ui-monospace,Menlo,Consolas,monospace;color:var(--muted);word-break:break-all;margin-top:4px}
details summary{cursor:pointer;color:var(--muted);font-size:13px;margin-top:6px}
ul{margin:6px 0;padding-left:20px}table{width:100%;border-collapse:collapse}
td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);font-size:14px;vertical-align:top}
img.shot{max-width:100%;border:1px solid var(--line);border-radius:6px;margin-top:8px}
.filters{display:flex;gap:8px;flex-wrap:wrap}.filters button{border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:99px;padding:4px 12px;cursor:pointer;font:inherit;font-size:13px}
.filters button[aria-pressed=true]{background:var(--text);color:var(--bg)}
.good{color:var(--ok);font-weight:600}
</style></head><body><main>
<h1>Glitch Report</h1>
<div class="muted">${esc(report.start)} · ${report.results.length} pages scanned · ${esc(new Date(report.startedAt).toLocaleString())}</div>

<div class="stats">
  <div class="stat s-crit"><b>${c.critical}</b>Critical</div>
  <div class="stat s-warn"><b>${c.warning}</b>Warnings</div>
  <div class="stat s-info"><b>${c.info}</b>Info</div>
  <div class="stat"><b>${report.results.length}</b>Pages</div>
</div>
${c.critical + c.warning === 0 ? '<p class="good">No critical problems or warnings found.</p>' : ''}

<h2>Top issues across the site</h2>
<div class="filters" role="group" aria-label="Filter by severity">
  <button data-f="all" aria-pressed="true">All</button>
  <button data-f="critical" aria-pressed="false">Critical</button>
  <button data-f="warning" aria-pressed="false">Warnings</button>
  <button data-f="info" aria-pressed="false">Info</button>
</div>
<div id="issues">
${topIssues.map((g) => `<div class="card" data-sev="${g.severity}">
  <span class="pill ${g.severity}">${g.severity}</span><b>${esc(g.message)}</b>
  <span class="muted"> · ${g.pages.length} page${g.pages.length > 1 ? 's' : ''}</span>
  ${g.detail ? `<div class="detail">${esc(g.detail)}</div>` : ''}
  <details><summary>Where</summary><ul>${g.pages.slice(0, 50).map((u) => u.startsWith('(') ? `<li>${esc(u)}</li>` : `<li><a href="${esc(u)}">${esc(u)}</a></li>`).join('')}${g.pages.length > 50 ? `<li>…and ${g.pages.length - 50} more</li>` : ''}</ul></details>
</div>`).join('\n') || '<p class="muted">None.</p>'}
</div>

${report.discovered?.length ? `<h2>Pages found by clicking</h2><div class="card"><p class="muted">These pages have no normal link; the bot found them by clicking buttons and menus.</p><ul>${report.discovered.map((u) => `<li><a href="${esc(u)}">${esc(u)}</a></li>`).join('')}</ul></div>` : ''}

${linkSection('Broken links to files on your site', report.brokenFiles)}
${linkSection('Broken external links', report.brokenExternal)}

${report.duplicateTitles.length ? `<h2>Pages sharing the same title</h2>
${report.duplicateTitles.map((d) => `<div class="card"><b>${esc(d.title)}</b><ul>${d.urls.map((u) => `<li><a href="${esc(u)}">${esc(u)}</a></li>`).join('')}</ul></div>`).join('')}` : ''}

<h2>Pages with problems</h2>
${pages.map((r) => `<div class="card" data-sev="${['critical', 'warning', 'info'][worst(r)]}">
  <b><a href="${esc(r.url)}">${esc(r.url)}</a></b>
  <div class="muted">HTTP ${r.status ?? '—'} · ${r.loadMs ? (r.loadMs / 1000).toFixed(1) + 's' : '—'}${r.finalUrl !== r.url ? ` · ended at ${esc(r.finalUrl)}` : ''}</div>
  <ul>${[...r.issues].sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]).map((i) =>
    `<li><span class="pill ${i.severity}">${i.severity}</span>${esc(i.message)}${i.detail ? `<div class="detail">${esc(i.detail)}</div>` : ''}</li>`).join('')}</ul>
  ${r.linkedFrom ? `<details><summary>Linked from ${r.linkedFrom.length} page(s)</summary><ul>${r.linkedFrom.map((l) => `<li><a href="${esc(l.from)}">${esc(l.from)}</a> <span class="muted">“${esc(l.text)}”</span></li>`).join('')}</ul></details>` : ''}
  ${r.screenshot ? `<details><summary>Screenshot</summary><img class="shot" loading="lazy" src="${esc(r.screenshot)}" alt="Screenshot of ${esc(r.url)}"></details>` : ''}
</div>`).join('\n') || '<p class="muted">None.</p>'}

<h2>Slowest pages</h2>
<div class="card" style="overflow-x:auto"><table><tr><th>Load</th><th>Main content</th><th>Jumping</th><th>Size</th><th>Page</th></tr>
${slowest.map((r) => `<tr><td>${(r.loadMs / 1000).toFixed(2)}s</td><td>${r.vitals?.lcp ? (r.vitals.lcp / 1000).toFixed(1) + 's' : '—'}</td><td>${r.vitals ? r.vitals.cls : '—'}</td><td>${r.bytes ? (r.bytes / 1048576).toFixed(1) + ' MB' : '—'}</td><td><a href="${esc(r.url)}">${esc(r.url)}</a></td></tr>`).join('')}
</table></div>

${report.skipped.robots || report.skipped.filtered ? `<p class="muted">Skipped ${report.skipped.robots} URLs blocked by robots.txt and ${report.skipped.filtered} by your include/exclude filters.</p>` : ''}
</main>
<script>
document.querySelectorAll('.filters button').forEach((b) => b.addEventListener('click', () => {
  document.querySelectorAll('.filters button').forEach((x) => x.setAttribute('aria-pressed', x === b));
  document.querySelectorAll('#issues .card').forEach((card) => {
    card.hidden = b.dataset.f !== 'all' && card.dataset.sev !== b.dataset.f;
  });
}));
</script>
</body></html>`;
}

function worst(r) {
  return Math.min(...r.issues.map((i) => SEV_ORDER[i.severity]), 3);
}

function linkSection(title, list) {
  if (!list.length) return '';
  return `<h2>${esc(title)}</h2>
${list.map((b) => `<div class="card"><span class="pill critical">${b.status ?? 'error'}</span><a href="${esc(b.url)}">${esc(b.url)}</a>
${b.error ? `<div class="detail">${esc(b.error)}</div>` : ''}
<details><summary>Linked from ${b.linkedFrom.length} page(s)</summary><ul>${b.linkedFrom.map((l) => `<li><a href="${esc(l.from)}">${esc(l.from)}</a> <span class="muted">“${esc(l.text)}”</span></li>`).join('')}</ul></details></div>`).join('\n')}`;
}
