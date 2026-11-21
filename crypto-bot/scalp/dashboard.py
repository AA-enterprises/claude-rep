"""Local dashboard (sirf aapke PC par): open positions live PnL ke saath, trade history, equity chart."""
from __future__ import annotations

import csv
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _read_json(path: str):
    for _ in range(5):
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.1)
    return None


def _read_csv(path: str) -> list[dict]:
    try:
        with open(path, newline="") as f:
            return list(csv.DictReader(f))
    except (FileNotFoundError, PermissionError):
        return []


def build_state(state_path: str, trades_path: str, equity_path: str, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    st = _read_json(state_path)
    if not st:
        return {"status": "no_state"}
    pending = set()
    try:
        with open(state_path.replace(".json", "_commands.jsonl"), encoding="utf-8") as f:
            pending = {json.loads(x).get("symbol") for x in f if x.strip()}
    except (OSError, ValueError):
        pass
    acct, prices = st["account"], st.get("prices", {})
    fee_rate, slip = st.get("fee_rate", 0.0005), st.get("slippage_pct", 0.0002)
    positions, unreal, fees_open, net_if_closed = [], 0.0, 0.0, 0.0
    for p in acct["positions"]:
        mark = prices.get(p["symbol"], p["entry"])
        d = 1 if p["side"] == "LONG" else -1
        pnl = d * (mark - p["entry"]) * p["qty"]
        unreal += pnl
        liq = p.get("liq") or p["entry"] * (1 - d * max(0.0, 1 / p["leverage"] - 0.005))      # purani state mein liq nahi hota
        exit_cost = p["qty"] * mark * (fee_rate + slip)                 # abhi band karein to: exit fee + slippage
        fees_est = p.get("entry_fee", 0.0) + exit_cost                  # entry fee pehle hi balance se kat chuki hai
        fees_open += fees_est
        net_if_closed += pnl - fees_est
        positions.append({
            "entry_fee": p.get("entry_fee", 0.0), "fees_est": fees_est, "net_if_closed": pnl - fees_est,
            "liq": liq, "liq_dist": abs(liq / mark - 1), "closing": p["symbol"] in pending,
            "manual": bool(p.get("manual")), "method": p.get("method", ""), "trail_active": p.get("trail_dist", 0) > 0 and ((p["side"] == "LONG" and p["sl"] > p["entry"]) or (p["side"] == "SHORT" and p["sl"] < p["entry"])), "symbol": p["symbol"], "side": p["side"], "leverage": p["leverage"], "qty": p["qty"],
            "notional": p["qty"] * p["entry"], "margin": p["margin"], "entry": p["entry"], "mark": mark,
            "tp": p["tp"], "sl": p["sl"], "pnl": pnl, "roi": pnl / p["margin"] if p["margin"] else 0.0,
            "held_min": (now * 1000 - p["opened_ts"]) / 60000, "score": p.get("score", 0),
            "max_hold_min": p["max_hold_ms"] / 60000,
        })
    positions.sort(key=lambda x: x["held_min"])   # nayi trade upar
    rows = _read_csv(trades_path)
    wins = sum(float(r["pnl"]) > 0 for r in rows)
    total = sum(float(r["pnl"]) for r in rows)
    trades = [{**r, "fees": float(r.get("fees") or 0), "pnl": float(r["pnl"]), "roi": float(r["roi"]), "entry": float(r["entry"]),
               "exit": float(r["exit"]), "held_min": float(r["held_min"]), "closed_ts": int(float(r["closed_ts"]))}
              for r in rows[-100:]][::-1]
    days: dict[str, dict] = {}
    for r in rows:
        pnl = float(r["pnl"])
        day = time.strftime("%Y-%m-%d", time.localtime(float(r["closed_ts"]) / 1000))
        d = days.setdefault(day, {"day": day, "n": 0, "wins": 0, "losses": 0, "profit": 0.0, "loss": 0.0, "net": 0.0, "fees": 0.0})
        d["n"] += 1
        d["fees"] += float(r.get("fees") or 0)
        d["net"] += pnl
        if pnl > 0:
            d["wins"] += 1
            d["profit"] += pnl
        else:
            d["losses"] += 1
            d["loss"] += pnl
    today_key = time.strftime("%Y-%m-%d", time.localtime(now))
    today = days.get(today_key, {"day": today_key, "n": 0, "wins": 0, "losses": 0, "profit": 0.0, "loss": 0.0, "net": 0.0, "fees": 0.0})
    all_fees = sum(float(r.get("fees") or 0) for r in rows)
    coins: dict[str, dict] = {}
    for r in rows:
        c = coins.setdefault(r["symbol"], {"symbol": r["symbol"], "n": 0, "wins": 0, "fees": 0.0, "net": 0.0})
        f = float(r.get("fees") or 0)
        pnl = float(r["pnl"])
        c["n"] += 1
        c["wins"] += pnl > 0
        c["fees"] += f
        c["net"] += pnl                                          # pnl pehle se fees ke baad hai
    for c in coins.values():
        c["gross"] = c["net"] + c["fees"]                        # fees se pehle
    by_coin = sorted(coins.values(), key=lambda c: -c["fees"])
    daily = sorted(days.values(), key=lambda d: d["day"], reverse=True)[:60]
    eq = [[int(r["ts"]), float(r["equity"])] for r in _read_csv(equity_path)[-1500:]]
    start = st.get("start_balance", acct["balance"])
    equity = acct["balance"] + unreal
    age = now - st.get("updated", 0)
    return {
        "status": "running" if age < 60 else "stale", "age_sec": age,
        "fees_open": fees_open, "net_if_closed": net_if_closed, "fees_all": all_fees, "by_coin": by_coin,
        "balance": acct["balance"], "equity": equity, "unrealized": unreal, "start_balance": start,
        "return_pct": equity / start - 1 if start else 0.0,
        "today": today, "daily": daily, "positions": positions, "trades": trades, "equity_series": eq,
        "stats": {"n": len(rows), "wins": int(wins), "win_rate": wins / len(rows) if rows else 0.0, "pnl": total},
    }


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scalp Bot Dashboard</title><style>
:root{--bg:#0b0e11;--panel:#181a20;--line:#2b3139;--tx:#eaecef;--mut:#848e9c;--up:#0ecb81;--dn:#f6465d;--acc:#fcd535}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--line)}
h1{font-size:17px;margin:0;font-weight:600}.pill{padding:2px 10px;border-radius:999px;font-size:12px;border:1px solid var(--line);color:var(--mut)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:var(--mut)}
.run .dot{background:var(--up)}.stale .dot{background:var(--dn)}
main{padding:16px 20px;max-width:1300px;margin:auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card .k{color:var(--mut);font-size:12px}.card .v{font-size:20px;font-weight:600;margin-top:2px;font-variant-numeric:tabular-nums}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin-top:14px}
.tabs{display:flex;gap:4px;padding:8px 12px 0;border-bottom:1px solid var(--line)}
.tab{padding:8px 14px;color:var(--mut);cursor:pointer;border-bottom:2px solid transparent;background:none;border-top:0;border-left:0;border-right:0;font:inherit}
.tab.on{color:var(--tx);border-bottom-color:var(--acc)}
.tw{overflow-x:auto}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{color:var(--mut);font-weight:400;font-size:12px;text-align:right;padding:10px 12px;white-space:nowrap}td{padding:10px 12px;text-align:right;border-top:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}.up{color:var(--up)}.dn{color:var(--dn)}.mut{color:var(--mut)}
.tag{font-size:11px;padding:1px 6px;border-radius:4px;margin-left:6px}.tag.LONG{background:#0ecb8122;color:var(--up)}.tag.SHORT{background:#f6465d22;color:var(--dn)}
.btn{background:none;border:1px solid var(--dn);color:var(--dn);border-radius:6px;padding:3px 10px;font:inherit;font-size:12px;cursor:pointer}.btn:hover{background:#f6465d22}.btn:disabled{opacity:.5;cursor:default}
.empty{padding:28px;text-align:center;color:var(--mut)}canvas{width:100%;height:200px;display:block}
</style></head><body>
<header><h1>Scalp Bot</h1><span class="pill">Paper</span><span id="st" class="pill"><span class="dot"></span><span id="stt">...</span></span><span class="mut" id="upd"></span></header>
<main>
<div class="cards" id="cards"></div>
<div class="panel"><div class="tabs"><button class="tab on" data-t="pos">Open Positions (<span id="np">0</span>)</button><button class="tab" data-t="daily">Daily P&amp;L</button><button class="tab" data-t="hist">Trade History</button><button class="tab" data-t="coins">Coins (fees)</button><button class="tab" data-t="eq">Equity</button></div>
<div id="pos" class="tw"></div><div id="daily" class="tw" hidden></div><div id="hist" class="tw" hidden></div><div id="coins" class="tw" hidden></div><div id="eq" hidden style="padding:12px"><canvas id="cv" width="1200" height="400"></canvas></div></div>
</main><script>
const $=id=>document.getElementById(id);
const fp=p=>p>=100?p.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}):p>=1?p.toFixed(4):p.toFixed(6);
const fm=(x,d=2)=>(x>=0?"+":"")+x.toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
const nm=s=>s.split(":")[0].replace("/","");
const dur=m=>{m=Math.floor(m);return m>=60?Math.floor(m/60)+"h "+(m%60)+"m":m+"m"};
const cls=x=>x>0?"up":x<0?"dn":"";
function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e}
function card(k,v,c){const d=el("div","card");d.append(el("div","k",k),el("div","v "+(c||""),v));return d}
function table(head,rows){const t=el("table"),h=el("tr");head.forEach(x=>h.append(el("th","",x)));t.append(h);
 rows.forEach(r=>{const tr=el("tr");r.forEach(c=>{const td=el("td",c.c||"");if(c.btn){const b=el("button","btn",c.label);b.disabled=!!c.off;b.onclick=ev=>c.onclick(ev.target);td.append(b)}else if(c.n){const s=el("span","",c.t);td.append(s,el("span","tag "+c.n,c.n))}else td.textContent=c.t??c;tr.append(td)});t.append(tr)});return t}
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{document.querySelectorAll(".tab").forEach(x=>x.classList.toggle("on",x===b));
 ["pos","daily","hist","coins","eq"].forEach(i=>$(i).hidden=i!==b.dataset.t);draw()});
let S=null;
function chart(){const cv=$("cv"),c=cv.getContext("2d"),w=cv.width,h=cv.height;c.clearRect(0,0,w,h);
 const d=S&&S.equity_series;if(!d||d.length<2){c.fillStyle="#848e9c";c.font="20px sans-serif";c.fillText("Equity data thodi der mein aayega (har 60s ek point)",20,40);return}
 const ys=d.map(p=>p[1]),mn=Math.min(...ys),mx=Math.max(...ys),pad=(mx-mn)*.1||1,lo=mn-pad,hi=mx+pad,t0=d[0][0],t1=d[d.length-1][0]||1;
 const X=t=>40+(t-t0)/(t1-t0||1)*(w-60),Y=v=>h-30-(v-lo)/(hi-lo)*(h-50);
 c.strokeStyle="#2b3139";c.fillStyle="#848e9c";c.font="16px sans-serif";c.lineWidth=1;
 for(let i=0;i<=4;i++){const v=lo+(hi-lo)*i/4,y=Y(v);c.beginPath();c.moveTo(40,y);c.lineTo(w-20,y);c.stroke();c.fillText(v.toFixed(0),2,y-3)}
 c.strokeStyle=ys[ys.length-1]>=ys[0]?"#0ecb81":"#f6465d";c.lineWidth=2.5;c.beginPath();d.forEach((p,i)=>i?c.lineTo(X(p[0]),Y(p[1])):c.moveTo(X(p[0]),Y(p[1])));c.stroke()}
function draw(){if(!S)return;if(!$("eq").hidden)chart()}
function render(s){S=s;const st=$("st");
 if(s.status==="no_state"){$("stt").textContent="Bot ne abhi state file nahi banayi";$("cards").replaceChildren();$("pos").replaceChildren(el("div","empty","Pehle bot chalao: python main.py scalp-paper"));return}
 st.className="pill "+(s.status==="running"?"run":"stale");$("stt").textContent=s.status==="running"?"Bot running":"Bot ruka hua / data purana";
 $("upd").textContent="update "+Math.round(s.age_sec)+"s pehle";
 const T=s.today,c=$("cards");c.replaceChildren(
  card("Aaj ka Profit ("+T.wins+" trades)",fm(T.profit),T.profit>0?"up":""),card("Aaj ka Loss ("+T.losses+" trades)",fm(T.loss),T.loss<0?"dn":""),
  card("Aaj ka Net (closed)",fm(T.net),cls(T.net)),card("Unrealized PnL",fm(s.unrealized),cls(s.unrealized)),card("Abhi sab band karein (fees ke baad)",fm(s.net_if_closed),cls(s.net_if_closed)),card("Fees aaj / total",T.fees.toFixed(2)+" / "+s.fees_all.toFixed(2),"dn"),
  card("Equity (USDT)",s.equity.toLocaleString(undefined,{maximumFractionDigits:2}),cls(s.return_pct)),
  card("Total Return",fm(s.return_pct*100)+"%",cls(s.return_pct)),card("All-time Closed PnL",fm(s.stats.pnl),cls(s.stats.pnl)),
  card("Win rate (all-time)",s.stats.n?(s.stats.win_rate*100).toFixed(0)+"% ("+s.stats.wins+"/"+s.stats.n+")":"-"));
 $("daily").replaceChildren(s.daily.length?table(["Date","Trades","Won / Lost","Profit","Loss","Fees","Net PnL"],
  s.daily.map(d=>[d.day+(d.day===T.day?"  (aaj)":""),d.n,d.wins+" / "+d.losses,{t:fm(d.profit),c:d.profit>0?"up":""},{t:fm(d.loss),c:d.loss<0?"dn":""},{t:"-"+(d.fees||0).toFixed(2),c:"mut"},{t:fm(d.net),c:cls(d.net)}])):el("div","empty","Abhi koi closed trade nahi"));
 $("np").textContent=s.positions.length;
 $("pos").replaceChildren(s.positions.length?table(["Symbol","Size (USDT)","Margin","Entry","Mark","TP","SL","Liq. Price","PnL (ROI%)","Fees (est.)","Net abhi band","Held",""],
  s.positions.map(p=>[{t:nm(p.symbol)+" "+p.leverage+"x",n:p.side},fp(p.notional).replace(/\.\d+$/,""),p.margin.toFixed(2),fp(p.entry),fp(p.mark),{t:p.tp==null?"trail":fp(p.tp),c:"up"},{t:fp(p.sl),c:"dn"},{t:fp(p.liq)+" ("+(p.liq_dist*100).toFixed(0)+"%)",c:p.liq_dist<0.1?"dn":"mut"},
   {t:fm(p.pnl)+" ("+fm(p.roi*100,1)+"%)",c:cls(p.pnl)},{t:"-"+p.fees_est.toFixed(2),c:"mut"},{t:fm(p.net_if_closed),c:cls(p.net_if_closed)},dur(p.held_min)+" / "+dur(p.max_hold_min),{btn:true,label:p.closing?"band ho rahi...":"CLOSE",off:p.closing,onclick:b=>closePos(p.symbol,b)}])):el("div","empty","Abhi koi open trade nahi"));
 $("coins").replaceChildren(s.by_coin.length?table(["Coin","Trades","Won","Fees paid","Gross (fees se pehle)","Net (fees ke baad)"],
  s.by_coin.map(c=>[nm(c.symbol),c.n,c.wins+" / "+c.n,{t:"-"+c.fees.toFixed(2),c:"dn"},{t:fm(c.gross),c:cls(c.gross)},{t:fm(c.net),c:cls(c.net)}])):el("div","empty","Abhi koi closed trade nahi"));
 $("hist").replaceChildren(s.trades.length?table(["Symbol","Entry","Exit","Result","PnL (ROI%)","Fees","Held","Closed (UTC)"],
  s.trades.map(t=>[{t:nm(t.symbol),n:t.side},fp(t.entry),fp(t.exit),{t:t.reason,c:(t.reason==="TP"||t.reason==="TRAIL")?"up":t.reason==="SL"?"dn":"mut"},
   {t:fm(t.pnl)+" ("+fm(t.roi*100,1)+"%)",c:cls(t.pnl)},{t:"-"+t.fees.toFixed(2),c:"mut"},dur(t.held_min),new Date(t.closed_ts).toISOString().slice(0,16).replace("T"," ")])):el("div","empty","Abhi koi closed trade nahi"));
 draw()}
async function closePos(sym,btn){
 if(!confirm(nm(sym)+" trade ko abhi market price par band karein?"))return;
 btn.disabled=true;btn.textContent="bhej rahi...";
 try{const r=await fetch("/api/close",{method:"POST",headers:{"Content-Type":"application/json","X-Requested-With":"scalp-dashboard"},body:JSON.stringify({symbol:sym})});
  const j=await r.json();if(!j.ok){alert(j.error||"request fail");btn.disabled=false;btn.textContent="CLOSE";return}
  btn.textContent="band ho rahi..."}catch(e){alert("Dashboard se connection nahi");btn.disabled=false;btn.textContent="CLOSE"}
 setTimeout(tick,3000)}
async function tick(){try{const r=await fetch("/api/state");render(await r.json())}catch(e){$("stt").textContent="Dashboard server se connection nahi"}}
tick();setInterval(tick,3000);
</script></body></html>"""


def make_handler(state_path: str, trades_path: str, equity_path: str, poll: dict | None = None):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.split("?")[0] == "/api/state":
                if poll is not None:
                    poll["t"] = time.time()                  # koi browser tab dashboard dekh raha hai
                body, ctype = json.dumps(build_state(state_path, trades_path, equity_path)).encode(), "application/json"
            elif self.path.split("?")[0] == "/":
                body, ctype = PAGE.encode("utf-8"), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _safe(self) -> bool:
            """Sirf aapke apne dashboard page se aayi request (dusri website se nahi): Host/Origin/custom header check."""
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            return (host.split(":")[0] in ("127.0.0.1", "localhost")
                    and (origin is None or origin == f"http://{host}")
                    and self.headers.get("X-Requested-With") == "scalp-dashboard"
                    and self.headers.get("Content-Type", "").startswith("application/json"))

        def _json(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            if self.path.split("?")[0] != "/api/close":
                return self._json(404, {"ok": False, "error": "not found"})
            if not self._safe():
                return self._json(403, {"ok": False, "error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                sym = str(json.loads(self.rfile.read(min(n, 4096)) or b"{}").get("symbol", ""))
            except (ValueError, TypeError):
                return self._json(400, {"ok": False, "error": "bad request"})
            st = _read_json(state_path) or {}
            if sym not in {p["symbol"] for p in st.get("account", {}).get("positions", [])}:
                return self._json(404, {"ok": False, "error": "ye position ab open nahi hai"})
            with open(state_path.replace(".json", "_commands.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"action": "close", "symbol": sym, "ts": time.time()}) + "\n")
            self._json(200, {"ok": True})

        def log_message(self, *a):  # console shaant
            pass
    return H


def _open_if_no_tab(poll: dict, url: str, delay: float) -> None:
    """`delay` second ruk ke dekho: kisi purane tab ne dashboard poll kiya? Haan to naya tab nahi kholte (wo khud refresh ho jata hai)."""
    t0 = time.time()
    time.sleep(delay)
    if poll["t"] < t0:
        import webbrowser
        webbrowser.open(url)


def serve(state_path: str, trades_path: str, port: int = 8050, open_browser: bool = True) -> None:
    equity_path = state_path.replace(".json", "_equity.csv")
    poll = {"t": 0.0}
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state_path, trades_path, equity_path, poll))
    url = f"http://127.0.0.1:{port}"
    print(f"Dashboard: {url}  (sirf aapke PC par; band karne ke liye Ctrl+C)")
    if open_browser:
        threading.Thread(target=_open_if_no_tab, args=(poll, url, 4.0), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def start_background(state_path: str, trades_path: str, port: int = 8050, open_browser: bool = False, open_delay: float = 5.0):
    """Dashboard ko bot ke saath hi background thread mein chalata hai (alag command ki zaroorat nahi).
    Port pehle se use mein ho (dashboard alag chal raha ho) to chupchap skip, None return."""
    equity_path = state_path.replace(".json", "_equity.csv")
    poll = {"t": 0.0}
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state_path, trades_path, equity_path, poll))
    except OSError:
        print(f"Dashboard port {port} pehle se use mein hai (shayad alag chal raha hai): http://127.0.0.1:{port}")
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    print(f"Dashboard: {url}  (bot ke saath chalta hai, alag command ki zaroorat nahi)")
    if open_browser:                                           # naya tab sirf tab, jab koi dashboard tab pehle se khula na ho
        threading.Thread(target=_open_if_no_tab, args=(poll, url, open_delay), daemon=True).start()
    return srv
