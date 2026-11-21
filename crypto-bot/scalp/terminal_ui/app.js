"use strict";
const $ = (s, r = document) => r.querySelector(s);
const PKT = 5 * 3600;
let DATA = null, VIEW = "overview", TOAST_T;
const ui = {lastT: 0, chart: null, candles: null, volume: null, sym: null, tf: "5m", lines: [], timer: null, msg: null};
const sel = {cand: null, cands: null, loading: false, tab: "pos", day: null};

/* ---------- helpers ---------- */
const nm = s => s.split(":")[0].replace("/", "");
const fp = p => p >= 100 ? p.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : p >= 1 ? p.toFixed(4) : p.toFixed(6);
const fm = (x, d = 2) => (x >= 0 ? "+" : "") + x.toLocaleString(undefined, {minimumFractionDigits: d, maximumFractionDigits: d});
const money = x => "$" + x.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
const cls = x => x > 0 ? "up" : x < 0 ? "dn" : "";
const dur = m => { m = Math.floor(m); return m >= 60 ? Math.floor(m / 60) + "h " + (m % 60) + "m" : m + "m"; };
const pad2 = n => String(n).padStart(2, "0");
function pk(ms) { const d = new Date(ms + PKT * 1000); return `${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`; }
function el(tag, c, t) { const e = document.createElement(tag); if (c) e.className = c; if (t !== undefined) e.textContent = t; return e; }
function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("show"); clearTimeout(TOAST_T); TOAST_T = setTimeout(() => t.classList.remove("show"), 3500); }
async function api(path, body) {
  const opt = body ? {method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "scalp-terminal"}, body: JSON.stringify(body)} : {};
  const r = await fetch(path, opt); let j = null; try { j = await r.json(); } catch (e) {}
  if (!r.ok && !(j && j.error)) throw new Error("server error " + r.status);
  return j;
}
function table(head, rows) {
  const t = el("table"), th = el("thead"), hr = el("tr"); head.forEach(h => hr.append(el("th", "", h))); th.append(hr); t.append(th);
  const tb = el("tbody");
  rows.forEach(r => { const tr = el("tr", r.cls || ""); (r.cells || r).forEach(c => {
    const td = el("td", c.c || "");
    if (c.nodes) c.nodes.forEach(n => td.append(n));
    else if (c.side) { td.append(el("span", "", c.t), el("span", "tag " + c.side, c.side)); if (c.manual) td.append(el("span", "tag MANUAL", "MANUAL")); }
    else td.textContent = c.t !== undefined ? c.t : c;
    tr.append(td); });
    if (r.onclick) tr.onclick = r.onclick; tb.append(tr); });
  t.append(tb); const w = el("div", "table-scroll"); w.append(t); return w;
}
const empty = (t, s) => { const d = el("div", "empty-state"); d.append(el("strong", "", t)); if (s) d.append(el("small", "", s)); return d; };
const botById = id => DATA && DATA.bots.find(b => b.id === id);

/* ---------- chart ---------- */
function initChart(container) {
  if (ui.chart) { ui.chart.remove(); ui.chart = null; }
  const LW = window.LightweightCharts;
  if (!LW) { container.textContent = "Chart library load nahi hui"; return; }
  const tickFmt = t => { const d = new Date((t + PKT) * 1000); return `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`; };
  ui.chart = LW.createChart(container, {
    layout: {background: {color: "#11161d"}, textColor: "#85909e", fontFamily: "Consolas, monospace", fontSize: 11},
    grid: {vertLines: {color: "#1a222b"}, horzLines: {color: "#1a222b"}}, rightPriceScale: {borderColor: "#252d38"},
    timeScale: {borderColor: "#252d38", timeVisible: true, secondsVisible: false, tickMarkFormatter: tickFmt},
    localization: {timeFormatter: t => { const d = new Date((t + PKT) * 1000); return `${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ${tickFmt(t)} PKT`; }},
    crosshair: {mode: 0}, autoSize: true,
  });
  ui.candles = ui.chart.addCandlestickSeries({upColor: "#13b981", downColor: "#f15b68", wickUpColor: "#13b981", wickDownColor: "#f15b68", borderVisible: false});
  ui.volume = ui.chart.addHistogramSeries({priceFormat: {type: "volume"}, priceScaleId: "vol"});
  ui.chart.priceScale("vol").applyOptions({scaleMargins: {top: 0.85, bottom: 0}});
  ui.lines = [];
}
function setLines(defs) {
  if (!ui.candles) return;
  ui.lines.forEach(l => { try { ui.candles.removePriceLine(l); } catch (e) {} }); ui.lines = [];
  defs.forEach(d => ui.lines.push(ui.candles.createPriceLine({price: d.price, color: d.color, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: d.title})));
}
const candle = r => ({time: r[0], open: r[1], high: r[2], low: r[3], close: r[4]});
const vol = r => ({time: r[0], value: r[5], color: r[4] >= r[1] ? "#13b98155" : "#f15b6855"});
async function loadChart() {
  if (!ui.sym || !ui.candles) return;
  const my = ui.sym + "|" + ui.tf;
  try {
    const rows = await api(`/api/klines?symbol=${encodeURIComponent(ui.sym)}&tf=${ui.tf}&limit=300`);
    if (ui.sym + "|" + ui.tf !== my || !Array.isArray(rows)) { if (rows && rows.error) chartMsg(rows.error); return; }
    ui.lastT = rows.length ? rows[rows.length - 1][0] : 0; ui.candles.setData(rows.map(candle)); ui.volume.setData(rows.map(vol)); ui.chart.timeScale().fitContent(); chartMsg("");
    legend(rows[rows.length - 1]);
  } catch (e) { chartMsg("Chart ka data nahi mila (Binance se connection?)"); }
}
async function tickChart() {
  if (!ui.sym || !ui.candles || document.hidden) return;
  const my = ui.sym + "|" + ui.tf;
  try {
    const rows = await api(`/api/klines?symbol=${encodeURIComponent(ui.sym)}&tf=${ui.tf}&limit=2`);
    if (ui.sym + "|" + ui.tf !== my || !Array.isArray(rows)) return;
    rows.forEach(r => { if (r[0] >= ui.lastT) { ui.candles.update(candle(r)); ui.volume.update(vol(r)); ui.lastT = r[0]; } }); chartMsg(""); legend(rows[rows.length - 1]);
  } catch (e) { chartMsg("live data ruk gaya, dobara koshish..."); }
}
function chartMsg(t) { if (ui.msg) ui.msg.textContent = t; }
function legend(r) {
  const l = $("#legend"); if (!l || !r) return;
  l.replaceChildren(); [["O", r[1]], ["H", r[2]], ["L", r[3]], ["C", r[4]]].forEach(([k, v]) => { const s = el("span", "", k + " "); s.append(el("b", "", fp(v))); l.append(s); });
  const p = $("#last-price"); if (p) p.textContent = fp(r[4]);
}
function selectSymbol(sym, lines) {
  ui.sym = sym; $("#chart-sym").textContent = nm(sym) + " · Perp"; setLines([]); loadChart().then(() => setLines(lines || []));
}
function linesForPos(p) {
  return [{price: p.entry, color: "#e5b54e", title: "Entry"}, {price: p.sl, color: "#f15b68", title: "SL"}, {price: p.liq, color: "#a35bd6", title: "Liq"}];
}

/* ---------- navigation ---------- */
function nav() {
  const n = $("#nav"); n.replaceChildren();
  const items = [["overview", "Overview", "◫"]].concat(DATA ? DATA.bots.map(b => [b.id, b.label, "◉"]) : []);
  items.forEach(([id, label, icon]) => {
    const a = el("a", "nav-item" + (id === VIEW ? " active" : "")); a.href = "#" + id;
    a.append(el("span", "nav-icon", icon), document.createTextNode(label)); n.append(a);
  });
}
function go(id) {
  VIEW = id; sel.cand = null; sel.cands = null; sel.tab = "pos"; sel.day = null; ui.sym = null; nav();
  $("#crumb").textContent = id === "overview" ? "Overview" : (botById(id) ? botById(id).label : id);
  id === "overview" ? renderOverview() : buildBotView(id);
}
window.addEventListener("hashchange", () => go(location.hash.slice(1) || "overview"));

/* ---------- overview ---------- */
function renderOverview() {
  const v = $("#view"); v.replaceChildren(); clearInterval(ui.timer);
  const t = el("div", "view-title"); t.append(el("h1", "", "Teeno bots ek jagah"), el("span", "", "Asli · Freq · Big (paper). Section kholne ke liye card dabao.")); v.append(t);
  const g = el("div", "bot-cards"); g.id = "cards"; v.append(g); fillOverview();
}
function fillOverview() {
  const g = $("#cards"); if (!g || !DATA) return; g.replaceChildren();
  DATA.bots.forEach(b => {
    const s = b.state, c = el("div", "panel bot-card"); c.onclick = () => { location.hash = b.id; };
    c.append(el("h2", "", b.label));
    if (s.status === "no_state") { c.append(el("div", "kv", "Bot ne abhi data nahi banaya (bot chalao)")); g.append(c); return; }
    const kv = (k, v, cl) => { const d = el("div", "kv"); d.append(el("span", "", k)); const b2 = el("b", cl || "", v); d.append(b2); c.append(d); };
    kv("Status", s.status === "running" ? "Chal raha hai" : "Ruka hua / data purana", s.status === "running" ? "up" : "dn");
    kv("Equity", money(s.equity)); kv("Return", fm(s.return_pct * 100) + "%", cls(s.return_pct)); kv("Khuli trades", String(s.positions.length));
    kv("Aaj ka net", fm(s.today.net), cls(s.today.net)); kv("Unrealized", fm(s.unrealized), cls(s.unrealized)); g.append(c);
  });
}

/* ---------- bot view ---------- */
function buildBotView(id) {
  const b = botById(id), v = $("#view"); v.replaceChildren(); clearInterval(ui.timer);
  if (!b) { v.append(empty("Bot nahi mila")); return; }
  const t = el("div", "view-title"); t.append(el("h1", "", b.label), el("span", "", `${b.rules.timeframe} · ${b.rules.leverage}x default · paper`)); v.append(t);
  const about = el("section", "panel about-panel"); about.append(el("h3", "", "Ye bot kaise kaam karta hai"));
  const ul = el("ul"); b.about.forEach(x => ul.append(el("li", "", x))); about.append(ul); v.append(about);
  const strip = el("section", "account-strip"); strip.id = "strip"; strip.style.marginTop = "12px"; v.append(strip);
  const grid = el("section", "trading-grid");
  const left = el("div", "left-column"), right = el("div", "right-column");
  const cp = el("section", "panel chart-panel");
  const ph = el("div", "panel-heading chart-heading"); const ht = el("div", "heading-title");
  const cs = el("strong", "", "Coin chuno"); cs.id = "chart-sym"; const lp = el("span", "mut", ""); lp.id = "last-price"; ht.append(cs, lp);
  const tools = el("div", "chart-tools"); const tfs = el("div", "timeframes");
  DATA.timeframes.forEach(tf => { const bt = el("button", tf === ui.tf ? "selected" : "", tf); bt.dataset.tf = tf;
    bt.onclick = () => { ui.tf = tf; tfs.querySelectorAll("button").forEach(x => x.classList.toggle("selected", x === bt)); loadChart(); }; tfs.append(bt); });
  tools.append(tfs); ph.append(ht, tools); cp.append(ph);
  const lg = el("div", "chart-legend"); lg.id = "legend"; cp.append(lg);
  const cw = el("div", "chart-wrap"); cw.style.position = "relative"; ui.msg = el("div", "chart-msg"); const ch = el("div"); ch.id = "chart"; cw.append(ui.msg, ch); cp.append(cw);
  const cf = el("div", "chart-footer"); cf.append(el("span", "", "Binance futures candles"), el("span", "", "Time: Pakistan (PKT)")); cp.append(cf);
  const pp = el("section", "panel positions-panel"); const tph = el("div", "panel-heading positions-heading"); const tabs = el("div", "tabs");
  [["pos", "Positions"], ["hist", "Trade History (24h)"], ["old", "Purani Trades"]].forEach(([k, l]) => { const bt = el("button", "tab" + (k === sel.tab ? " active" : ""), l); bt.dataset.k = k;
    bt.onclick = () => { sel.tab = k; sel.day = null; tabs.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === bt)); fillTabs(); }; tabs.append(bt); });
  tph.append(tabs); pp.append(tph); const body = el("div"); body.id = "tabbody"; pp.append(body);
  left.append(cp, pp);
  right.append(buildTakePanel(b), buildFindPanel(b)); grid.append(left, right); v.append(grid);
  initChart(ch); fillBot();
  const first = (b.state.positions || [])[0]; selectSymbol(first ? first.symbol : "BTC/USDT:USDT", first ? linesForPos(first) : []);
  ui.timer = setInterval(tickChart, 2000);
}
function strip(b) {
  const s = b.state, st = $("#strip"); if (!st) return; st.replaceChildren();
  if (s.status === "no_state") { st.append(el("div", "account-title", "Is bot ne abhi data nahi banaya: bot chalao")); return; }
  const m = (k, v, c) => { const d = el("div", "account-metric"); d.append(el("small", "", k), el("strong", c || "", v)); st.append(d); };
  const t = el("div", "account-title", b.label + " account"); t.append(el("span", "subtle-tag", "SIMULATED")); st.append(t);
  m("EQUITY", money(s.equity)); m("UNREALIZED", fm(s.unrealized), cls(s.unrealized)); m("BOT FREE MARGIN", money(s.free_margin));
  m("AAJ KA NET", fm(s.today.net), cls(s.today.net)); m("FEES (AAJ)", s.today.fees.toFixed(2)); m("RETURN", fm(s.return_pct * 100) + "%", cls(s.return_pct));
}
function fillBot() {
  const b = botById(VIEW); if (!b) return; strip(b); if (sel.tab !== "old") fillTabs();
  const s = b.state, dot = $("#conn-dot"), tx = $("#conn-text");
  tx.textContent = s.status === "running" ? b.label + " bot chal raha hai" : s.status === "no_state" ? b.label + " bot: data nahi" : b.label + " bot ruka hua / data purana";
  dot.style.background = s.status === "running" ? "#24c98d" : "#f15b68";
  const pe = $("#np"); if (pe) pe.textContent = (s.positions || []).length;
}
function fillTabs() {
  const b = botById(VIEW), body = $("#tabbody"); if (!b || !body) return; const s = b.state;
  body.replaceChildren();
  if (s.status === "no_state") { body.append(empty("Abhi data nahi", "Bot chalao, phir yahan trades dikhengi")); return; }
  if (sel.tab === "pos") {
    if (!s.positions.length) { body.append(empty("Abhi koi open trade nahi", "Find Trades se dhundo ya bot ke signal ka intezaar karo")); return; }
    body.append(table(["SYMBOL", "SIZE", "ENTRY", "MARK", "LIQ. PRICE", "MARGIN", "TP / SL", "PNL (ROE%)", "FEES (EST.)", "HELD", ""],
      s.positions.map(p => [{t: nm(p.symbol) + " " + p.leverage + "x", side: p.side, manual: p.manual}, money(p.notional).replace(/\.\d+$/, ""), fp(p.entry), fp(p.mark), {t: fp(p.liq) + " (" + (p.liq_dist * 100).toFixed(0) + "%)", c: p.liq_dist < 0.1 ? "dn" : "mut"},
        p.margin.toFixed(2), {t: (p.tp == null ? "trail" : fp(p.tp)) + " / " + fp(p.sl), c: "mut"}, {t: fm(p.pnl) + " (" + fm(p.roi * 100, 1) + "%)", c: cls(p.pnl)}, {t: "-" + p.fees_est.toFixed(2), c: "mut"}, dur(p.held_min) + " / " + dur(p.max_hold_min),
        {nodes: [btn("Open graph", false, () => { selectSymbol(p.symbol, linesForPos(p)); $("#chart").scrollIntoView({behavior: "smooth", block: "center"}); }),
                 btn(p.closing ? "band ho rahi..." : "CLOSE", p.closing, e => closePos(b, p, e.target), true)]}])));
  } else if (sel.tab === "hist") {
    const tr = s.trades24 || [];
    if (!tr.length) { body.append(empty("Pichhle 24 ghante mein koi band trade nahi", "24 ghante se purani trades 'Purani Trades' mein milengi")); return; }
    body.append(tradeTable(tr));
  } else {
    if (sel.day) { const back = el("button", "back-link", "← Saari tareekhein"); back.onclick = () => { sel.day = null; fillTabs(); }; body.append(back); loadDay(b, sel.day, body); return; }
    const days = b.archive_days || [];
    const note = el("div", "panel-note", `24 ghante se purani trades din ke hisaab se folder trade_archive/${b.id}/ mein save hoti hain (Pakistan ki tareekh). Din dabao to us din ki saari trades time ke hisaab se aayengi.`); body.append(note);
    if (!days.length) { body.append(empty("Abhi koi purani trade nahi", "Jab trade 24 ghante se purani ho jayegi yahan aa jayegi")); return; }
    body.append(table(["TAREEKH", "TRADES", "WON", "FEES", "NET PNL"], days.map(d => ({cls: "day-row", onclick: () => { sel.day = d.day; fillTabs(); },
      cells: [d.day, String(d.n), d.wins + " / " + d.n, {t: "-" + d.fees.toFixed(2), c: "mut"}, {t: fm(d.net), c: cls(d.net)}]}))));
  }
}
function btn(label, off, fn, danger) { const b = el("button", "mini-btn" + (danger ? " danger" : ""), label); b.disabled = !!off; b.onclick = fn; return b; }
function tradeTable(tr) {
  return table(["SYMBOL", "ENTRY", "EXIT", "RESULT", "PNL (ROI%)", "FEES", "HELD", "CLOSED (PKT)"],
    tr.map(t => [{t: nm(t.symbol), side: t.side, manual: String(t.manual) === "1" || t.manual === "True"}, fp(t.entry), fp(t.exit),
      {t: t.reason, c: (t.reason === "TP" || t.reason === "TRAIL") ? "up" : t.reason === "SL" ? "dn" : "mut"}, {t: fm(t.pnl) + " (" + fm(t.roi * 100, 1) + "%)", c: cls(t.pnl)},
      {t: "-" + Number(t.fees).toFixed(2), c: "mut"}, dur(t.held_min), pk(t.closed_ts)]));
}
async function loadDay(b, day, body) {
  body.append(el("div", "panel-note", day + " ki trades load ho rahi hain..."));
  try { const rows = await api(`/api/archive?bot=${b.id}&day=${day}`); body.lastChild.remove();
    if (!Array.isArray(rows) || !rows.length) { body.append(empty("Is din ki koi trade nahi")); return; }
    body.append(el("div", "panel-note", `${day}: ${rows.length} trades · net ${fm(rows.reduce((a, r) => a + r.pnl, 0))} USDT`)); body.append(tradeTable(rows));
  } catch (e) { body.lastChild.remove(); body.append(empty("Load nahi hua")); }
}
async function closePos(b, p, btnEl) {
  if (!confirm(nm(p.symbol) + " trade ko abhi market price par band karein?")) return;
  btnEl.disabled = true; btnEl.textContent = "bhej rahi...";
  try { const j = await api("/api/close", {bot: b.id, symbol: p.symbol}); if (!j.ok) { toast(j.error || "request fail"); btnEl.disabled = false; btnEl.textContent = "CLOSE"; return; } toast("Band karne ki request bhej di"); }
  catch (e) { toast("Terminal se connection nahi"); btnEl.disabled = false; btnEl.textContent = "CLOSE"; }
  setTimeout(refresh, 3000);
}

/* ---------- find trades + take trade ---------- */
function buildFindPanel(b) {
  const p = el("section", "panel"); const h = el("div", "panel-heading"); h.append(el("strong", "", "Find Trades · " + b.label)); p.append(h);
  const bar = el("div", "find-bar"); const fb = el("button", "mini-btn", "Find Trades"); fb.id = "find-btn"; fb.onclick = () => findTrades(b, true); bar.append(fb);
  const st = el("span", "mut", "Is bot ke rules se abhi ke trades dhundta hai"); st.id = "find-status"; bar.append(st); p.append(bar);
  const list = el("div", "cand-list"); list.id = "cands"; p.append(list);
  p.append(el("div", "find-note", "Signal = bot ki saari shartein poori. 'WEAK' = ek shart kam (apni marzi se lo). Har candidate ~1 ghante tak valid hai."));
  return p;
}
async function findTrades(b, refresh) {
  if (sel.loading) return; sel.loading = true; const fb = $("#find-btn"), st = $("#find-status"); fb.disabled = true; st.replaceChildren(el("span", "spin"), document.createTextNode("Scan ho raha hai (5-15 second)..."));
  try { const j = await api(`/api/signals?bot=${b.id}${refresh ? "&refresh=1" : ""}`); if (j.error) throw new Error(j.error);
    sel.cands = j; st.textContent = `${j.items.length} mile (${j.scanned} coins scan) · ${pk(j.found_ms)} PKT`; renderCands(b);
  } catch (e) { st.textContent = "Scan fail: " + (e.message || "network"); }
  sel.loading = false; fb.disabled = false;
}
function renderCands(b) {
  const l = $("#cands"); if (!l) return; l.replaceChildren(); const items = (sel.cands && sel.cands.items) || [];
  if (!items.length) { l.append(empty("Abhi is bot ke rules par koi trade nahi", "Market shaant hai. Thodi der baad dobara dabao")); return; }
  items.forEach(c => {
    const r = el("div", "cand" + (c.already_open ? " off" : "") + (sel.cand && sel.cand.symbol === c.symbol && sel.cand.side === c.side ? " sel" : ""));
    const a = el("div"); a.append(el("span", "", nm(c.symbol)), el("span", "tag " + c.side, c.side)); if (c.kind === "weak") a.append(el("span", "tag WEAK", "WEAK")); a.append(el("small", "", c.already_open ? "pehle se open" : `${c.score}/4 shartein (chahiye ${c.need})`));
    const m = el("div"); m.append(document.createTextNode(fp(c.price)), el("small", "", "ATR " + (c.atr_pct * 100).toFixed(1) + "%"));
    const z = el("div"); z.append(document.createTextNode("SL " + fp(c.sl_price)), el("small", "", "vol " + c.vol_ratio.toFixed(1) + "x"));
    r.append(a, m, z); if (!c.already_open) r.onclick = () => pickCand(b, c); l.append(r);
  });
}
function pickCand(b, c) {
  sel.cand = c; renderCands(b); const lv = $("#lev"); lv.value = c.suggested_leverage; $("#lev-r").value = c.suggested_leverage;
  const pool = DATA.pool, bs = b.state; const free = Math.min(pool.free, bs.free_margin || 0); const mg = $("#margin"); if (!mg.dataset.touched) mg.value = Math.max(0, Math.min(100, Math.floor(free))) || "";
  selectSymbol(c.symbol, [{price: c.price, color: "#e5b54e", title: "Signal price"}, {price: c.sl_price, color: "#f15b68", title: "Stop (bot rule)"}]); preview();
}
function buildTakePanel(b) {
  const p = el("section", "panel order-panel"); const h = el("div", "panel-heading order-title"); h.append(el("strong", "", "Trade lo (paper)"), el("span", "paper-small", "PAPER")); p.append(h);
  const sc = el("div", "sel-coin"); sc.id = "sel-coin"; sc.textContent = "Pehle Find Trades se ek coin chuno"; p.append(sc);
  const lab1 = el("label", "field-label", "Leverage "); lab1.append(el("span", "", "1x - 20x")); lab1.htmlFor = "lev"; p.append(lab1);
  const lr = el("div", "lev-row"); const w = el("div", "input-wrap"); const li = el("input"); li.id = "lev"; li.type = "number"; li.min = 1; li.max = 20; li.step = 1; li.value = b.rules.leverage; li.oninput = () => { $("#lev-r").value = li.value; preview(); }; w.append(li, el("span", "input-suffix", "x")); lr.append(w); p.append(lr);
  const sl = el("div", "percent-slider"); const ri = el("input"); ri.type = "range"; ri.id = "lev-r"; ri.min = 1; ri.max = 20; ri.value = b.rules.leverage; ri.oninput = () => { li.value = ri.value; preview(); }; sl.append(ri); p.append(sl);
  const hint = el("div", "hint"); hint.id = "lev-hint"; p.append(hint);
  const lab2 = el("label", "field-label", "Margin "); lab2.append(el("span", "", "USDT")); lab2.htmlFor = "margin"; p.append(lab2);
  const w2 = el("div", "input-wrap"); const mi = el("input"); mi.id = "margin"; mi.inputMode = "decimal"; mi.placeholder = "jaise 100"; mi.oninput = () => { mi.dataset.touched = "1"; preview(); }; w2.append(mi, el("span", "input-suffix", "USDT")); p.append(w2);
  const q = el("div", "quick"); [20, 50, 100, 200, 500, 1000].forEach(v => { const bt = el("button", "mini-btn", "$" + v); bt.onclick = () => { mi.value = v; mi.dataset.touched = "1"; preview(); }; q.append(bt); }); p.append(q);
  const sb = el("button", "submit-order long-submit", "Paper trade lo"); sb.id = "take-btn"; sb.disabled = true; sb.onclick = () => takeTrade(b); p.append(sb);
  const es = el("div", "order-estimates"); es.id = "est"; p.append(es);
  p.append(el("div", "order-disclaimer", "Paper trade: asli Binance order nahi jata. Trade bot hi kholta hai (~10 second)."));
  return p;
}
function preview() {
  const c = sel.cand, es = $("#est"), btn2 = $("#take-btn"), hint = $("#lev-hint"), sc = $("#sel-coin"); if (!es) return; es.replaceChildren();
  const b = botById(VIEW); if (!c) { btn2.disabled = true; return; }
  sc.replaceChildren(); sc.append(el("span", "", nm(c.symbol) + " " + c.side), el("span", c.kind === "weak" ? "warn" : "up", c.kind === "weak" ? "WEAK signal" : "Signal"));
  const lev = parseInt($("#lev").value, 10), mar = parseFloat($("#margin").value), mmr = b.rules.maint_margin_rate;
  btn2.className = "submit-order " + (c.side === "LONG" ? "long-submit" : "short-submit short"); btn2.textContent = (c.side === "LONG" ? "Paper Long lo" : "Paper Short lo");
  hint.replaceChildren(); hint.append(document.createTextNode(`Bot ki salah: ${c.suggested_leverage}x (zyada se zyada safe ${c.max_safe_leverage}x). Aap 1x se 20x tak kuch bhi le sakte ho.`));
  let ok = Number.isInteger(lev) && lev >= 1 && lev <= 20 && mar >= 1;
  const row = (k, v, cl) => { const d = el("div"); d.append(el("span", "", k), el("b", cl || "", v)); es.append(d); };
  if (ok) {
    const d = c.side === "LONG" ? 1 : -1, liqDist = 1 / lev - mmr, liq = c.price * (1 - d * liqDist), notional = mar * lev;
    row("Position size", money(notional)); row("Liquidation", fp(liq) + " (" + (liqDist * 100).toFixed(1) + "% door)", liqDist <= c.sl_pct ? "dn" : "");
    row("Bot ka stop", fp(c.sl_price) + " (" + (c.sl_pct * 100).toFixed(1) + "% door)"); row("Stop par loss (andaza)", "-" + money(notional * c.sl_pct), "dn"); row("Entry fee (andaza)", money(notional * b.rules.fee_rate));
    if (liqDist <= c.sl_pct) { ok = false; hint.append(el("div", "warn", `${lev}x par liquidation stop se pehle lag jayegi. ${c.max_safe_leverage}x ya kam lo.`)); }
    const pool = DATA.pool; if (mar > pool.free) { ok = false; hint.append(el("div", "warn", `Dashboard budget mein sirf ${money(pool.free)} free hai.`)); }
    if (mar > (b.state.free_margin || 0)) { ok = false; hint.append(el("div", "warn", `Is bot mein free margin sirf ${money(b.state.free_margin || 0)} hai.`)); }
  }
  btn2.disabled = !ok || b.state.status !== "running";
  if (b.state.status !== "running") hint.append(el("div", "warn", "Ye bot abhi chal nahi raha: pehle bot chalao."));
}
async function takeTrade(b) {
  const c = sel.cand; if (!c) return; const lev = parseInt($("#lev").value, 10), mar = parseFloat($("#margin").value);
  if (!confirm(`${nm(c.symbol)} ${c.side} · ${lev}x · margin ${mar} USDT (paper). Lein?`)) return;
  const bt = $("#take-btn"); bt.disabled = true;
  try { const j = await api("/api/take", {bot: b.id, symbol: c.symbol, side: c.side, leverage: lev, margin: mar}); toast(j.ok ? j.message : (j.error || "request fail")); if (j.ok) { sel.cand = null; $("#sel-coin").textContent = "Request bhej di, trade khulne ka intezaar..."; setTimeout(refresh, 4000); setTimeout(refresh, 11000); } }
  catch (e) { toast("Terminal se connection nahi"); }
  bt.disabled = false;
}

/* ---------- data loop ---------- */
function paintPool() {
  if (!DATA) return; const p = DATA.pool; $("#pool-free").textContent = money(p.free) + " free";
  $("#pool-text").textContent = `Budget ${money(p.total)} · lagi hui margin ${money(p.used)} (teeno bots ki haath wali trades)`;
}
async function refresh() {
  try {
    DATA = await api("/api/overview"); paintPool();
    if (!$("#nav").children.length || $("#nav").children.length !== DATA.bots.length + 1) nav();
    if (VIEW === "overview") fillOverview(); else if (botById(VIEW)) { fillBot(); preview(); }
    if (VIEW === "overview") { $("#conn-text").textContent = "Terminal chal raha hai"; $("#conn-dot").style.background = "#24c98d"; }
  } catch (e) { $("#conn-text").textContent = "Terminal server se connection nahi"; $("#conn-dot").style.background = "#f15b68"; }
}
(async function init() { await refresh(); go(location.hash.slice(1) || "overview"); setInterval(refresh, 3000); })();
