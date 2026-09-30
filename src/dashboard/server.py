"""Dashboard server — DeepCharts look, stdlib only (koi install nahi).

Kaam: background me market → HTF rukh → LTF signal → paper, har 20 sec.
Screen: http://localhost:8090 (3-sec auto-refresh).
Design: Dashboard design.md (LOCKED). Skills: dashboard-builder + frontend-patterns.
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.signal import generate_signal, htf_bias  # noqa: E402
from market.binance import fetch_klines  # noqa: E402
from market.validator import validate_candles  # noqa: E402
from paper.journal import Engine  # noqa: E402

SYMBOL = "BTCUSDT"
LTF, HTF = "5m", "1h"
ALL_TF = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]
TF_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
         "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
         "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000}
REFRESH_SEC = 20
CHART_TF = "5m"  # chart kis timeframe ka dikhega (button se badalta hai, signal hamesha 5m par)

STATE: dict = {"updated_at": 0, "ok": False, "error": "", "symbol": SYMBOL,
               "price": 0.0, "bias": "WAIT", "signal": None, "paper": {},
               "timeframes": {}, "log": [], "candles": []}
ENGINE = Engine()
LAST_CLOSED: dict = {}


def _note(msg: str) -> None:
    STATE["log"] = ([f"{time.strftime('%H:%M:%S')} {msg}"] + STATE["log"])[:10]


def refresh_once() -> None:
    try:
        ltf = fetch_klines(SYMBOL, LTF, 120)[:-1]  # band only (signal wala)
        htf = fetch_klines(SYMBOL, HTF, 120)[:-1]
        chart_candles = ltf if CHART_TF == LTF else (htf if CHART_TF == HTF else fetch_klines(SYMBOL, CHART_TF, 120)[:-1])
        for tf in ALL_TF:  # 12 TF live — signal wale dobara nahi, baki halka (10 candles)
            candles = ltf if tf == LTF else (htf if tf == HTF else fetch_klines(SYMBOL, tf, 11)[:-1])
            v = validate_candles(candles, TF_MS[tf])
            STATE["timeframes"][tf] = {"ok": v.valid, "score": v.score, "close": candles[-1].close,
                                    "chg": round((candles[-1].close - candles[0].close) / candles[0].close * 100, 2)}
            if tf in (LTF, HTF) and not v.valid:
                raise RuntimeError(f"{tf}: ganda data ({'; '.join(v.errors[:2])})")
        bias = htf_bias(htf, len(htf) - 1)
        STATE["bias"] = bias
        STATE["price"] = ltf[-1].close
        if LAST_CLOSED.get(LTF) != ltf[-1].time:  # nayi band candle
            LAST_CLOSED[LTF] = ltf[-1].time
            sig = generate_signal(ltf, len(ltf) - 1, bias=bias)
            if sig:
                ENGINE.queue(sig, LTF)
                STATE["signal"] = {"side": sig.side, "entry": sig.entry, "stop": sig.stop,
                                   "target": sig.target, "rr": round(sig.rr, 2),
                                   "event": sig.event, "reason": sig.reason}
                _note(f"signal {sig.side} {sig.event} RR {sig.rr:.1f}")
            else:
                STATE["signal"] = None
                _note(f"scan: rukh {bias}, koi entry nahi")
        ENGINE.on_candle(LTF, ltf[-1], TF_MS[LTF])
        STATE["paper"] = ENGINE.summary()
        eq, run = 10000.0, []
        for t in ENGINE.closed[-100:]:
            eq += t.pnl
            run.append(round(eq, 2))
        STATE["equity_curve"] = run  # P&L lakeer ke liye
        try:  # DOM depth (asli liquidity) — na aaye to screen nahi rukegi
            import requests as _rq
            dp = _rq.get("https://fapi.binance.com/fapi/v1/depth",
                         params={"symbol": SYMBOL, "limit": 20}, timeout=10).json()
            STATE["depth"] = {"bids": [[float(p), float(q)] for p, q in dp.get("bids", [])],
                              "asks": [[float(p), float(q)] for p, q in dp.get("asks", [])]}
            ag = _rq.get("https://fapi.binance.com/fapi/v1/aggTrades",
                         params={"symbol": SYMBOL, "limit": 100}, timeout=10).json()
            prints = []
            for t in ag:
                usd = float(t["p"]) * float(t["q"])
                if usd >= 25000:  # $25k+ = bada trade (whale)
                    prints.append({"p": float(t["p"]), "q": float(t["q"]),
                                   "usd": round(usd), "sell": bool(t["m"])})
            STATE["prints"] = prints[-15:]
        except Exception:
            pass
        STATE["candles"] = [{"t": c.time, "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume}
                            for c in chart_candles[-60:]]  # chart TF ki aakhri 60 band candles
        STATE["chart_tf"] = CHART_TF
        STATE["ok"] = True
        STATE["error"] = ""
        STATE["updated_at"] = int(time.time())
    except Exception as e:  # screen kabhi kaali nahi — error saaf dikhega
        STATE["ok"] = False
        STATE["error"] = str(e)[:200]
        _note(f"ERROR: {STATE['error']}")


def loop() -> None:
    while True:
        refresh_once()
        time.sleep(REFRESH_SEC)


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="10">
<title>Five Mark V1 — Live</title>
<style>*{box-sizing:border-box;margin:0;padding:0;font-family:Inter,'Segoe UI',Arial,sans-serif}
body{background:#030303;color:#f7f7f7;padding:12px}
.bar{display:flex;gap:12px;align-items:center;background:rgba(31,31,31,.7);border:1px solid rgba(255,255,255,.08);padding:10px 14px;border-radius:10px}
.logo{color:#8b5cf6;font-weight:800}.sym{font-weight:700;font-size:18px}.pr{color:#22c55e;font-weight:700;font-size:18px}
.st{margin-left:auto;font-size:13px}.ok{color:#22c55e}.bad{color:#ef4444}
.eng{margin-top:10px;background:rgba(31,31,31,.7);border:1px solid rgba(139,92,246,.4);border-radius:10px;padding:8px 14px;font-size:13px}
.grid{display:flex;gap:10px;margin-top:10px}.card{flex:1;background:#0b0b0d;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:12px}
.card h3{color:#8a8a8a;font-size:11px;letter-spacing:2px;margin-bottom:8px}
.big{font-size:20px;font-weight:800}.log{font-size:12px;color:#c9c9c9;line-height:1.7}
.note{margin-top:8px;color:#6a6a72;font-size:12px}.tf{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:#a8a8a8;padding:3px 10px;border-radius:20px;font-size:12px;cursor:pointer}.tf.on{background:#8b5cf6;color:#fff;border-color:#8b5cf6;font-weight:700}</style></head><body>
<div class="bar"><span class="logo">FIVE MARK V1</span><span class="sym">BTCUSDT</span><span class="tf" data-tf="1m" onclick="setTF('1m')">1m</span><span class="tf on" data-tf="5m" onclick="setTF('5m')">5m</span><span class="tf" data-tf="15m" onclick="setTF('15m')">15m</span><span class="tf" data-tf="1h" onclick="setTF('1h')">1h</span><span class="tf" data-tf="4h" onclick="setTF('4h')">4h</span><span class="tf" data-tf="1d" onclick="setTF('1d')">1d</span>
<span class="pr" id="p">…</span><span class="st" id="s">…</span></div>
<div class="eng" id="e">ENGINE: load ho raha hai…</div>
<div class="grid">
<div class="card"><h3>HTF RUKH (1h)</h3><div class="big" id="b">…</div></div>
<div class="card"><h3>SIGNAL (5m)</h3><div class="big" id="g">…</div></div>
<div class="card"><h3>PAPER ($10k)</h3><div class="big" id="w">…</div></div>
<div class="card"><h3>STRATEGY (90D jaisa)</h3><div class="big" id="st">…</div></div>
</div>
<div class="grid"><div class="card"><h3>12 TIMEFRAMES — LIVE (hara=OK)</h3><div id="tf" style="display:grid;grid-template-columns:repeat(6,1fr);gap:4px;font-size:12px"></div></div></div>
<div class="grid"><div class="card"><h3>P&L CURVE (CUMULATIVE)</h3><svg id="eq" width="100%" height="120"></svg></div></div>
<div class="grid"><div class="card"><h3 id="chh">CHART — 5m (LIVE)</h3><svg id="ch" width="100%" height="230"></svg></div></div>
<div class="grid"><div class="card"><h3>REPLAY (practice, pichla data)</h3>
<div style="font-size:13px;display:flex;gap:8px;align-items:center">
<select id="rtf"><option>5m</option><option>15m</option><option>1h</option><option>4h</option><option>1d</option></select>
<button id="rplay" style="background:#8b5cf6;color:#fff;border:none;padding:4px 14px;border-radius:14px;font-weight:700">Play</button>
<button id="rlive" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:4px 14px;border-radius:14px">Live</button>
<span id="rinfo" style="color:#8a8a8a"></span></div></div></div>
<div class="grid"><div class="card"><h3>BIG TRADES <button id="f25" style="background:#8b5cf6;color:#fff;border:none;padding:2px 10px;border-radius:10px;font-size:11px">$25k+</button> <button id="f100" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px;font-size:11px">$100k+</button></h3><div id="pr" style="font-size:12px;line-height:1.8"></div></div></div>
<div class="grid"><div class="card"><h3>DOM — ASLI LIQUIDITY (bids/asks)</h3><div id="dom" style="font-size:12px;line-height:1.8"></div></div></div>
<div class="grid"><div class="card"><h3>LOG (taza pehle)</h3><div class="log" id="l">…</div></div></div>
<p class="note">Live dashboard — 3-sec refresh. Design: Dashboard design.md (LOCKED).</p>
<script>
async function t(){try{const r=await fetch('/api/state',{cache:'no-store'});const d=await r.json();
document.getElementById('p').textContent=d.price||'…';
document.getElementById('s').innerHTML=d.ok?'<span class=ok>● DATA OK</span>':'<span class=bad>● '+d.error+'</span>';
document.getElementById('b').textContent=d.bias||'…';
document.getElementById('g').textContent=d.signal?(d.signal.side+' '+d.signal.event+' RR '+d.signal.rr):'koi entry nahi';
document.getElementById('w').textContent=d.paper.equity?('$'+d.paper.equity+' | '+d.paper.closed+' trades'):'…';
document.getElementById('st').textContent=d.paper?('Trades '+d.paper.closed+' | Win '+d.paper.win_rate+'% | Avg R:R '+d.paper.avg_r):'…';
document.getElementById('chh').textContent='CHART — '+(d.chart_tf||'5m')+' (LIVE)';document.getElementById('e').textContent='ENGINE: rukh '+d.bias+' | open '+((d.paper||{}).open||0)+' | '+(d.signal?('signal '+d.signal.side):'scan chal raha');
var esc=function(x){return String(x).split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;')};document.getElementById('l').innerHTML=(d.log||[]).map(esc).join('<br>');
let tfh='';['1m','3m','5m','15m','30m','1h','2h','4h','6h','8h','12h','1d'].forEach(k=>{const t=(d.timeframes||{})[k];
var ar=t&&t.chg!=null?(t.chg>=0?'▲ ':'▼ '):'';tfh+='<div style="padding:5px;border-radius:6px;text-align:center;background:'+(t&&t.ok?'rgba(34,197,94,.12)':'rgba(239,68,68,.12)')+';color:'+(t&&t.ok?'#22c55e':'#ef4444')+'">'+k+' '+ar+(t&&t.chg!=null?t.chg+'%':'')+'<br>'+(t?t.close:'…')+'</div>';});
document.getElementById('tf').innerHTML=tfh;
let dh='',mx=0;const dp=d.depth||{bids:[],asks:[]};(dp.bids||[]).concat(dp.asks||[]).forEach(x=>{mx=Math.max(mx,x[1]);});
(dp.asks||[]).slice().reverse().forEach(x=>{const w=(Math.log(1+x[1])/Math.log(1+(mx||1))*100).toFixed(0);
dh+='<div style="background:linear-gradient(90deg,rgba(239,68,68,.25) '+w+'%,transparent '+w+'%)">SELL '+x[0]+' ('+x[1]+')</div>';});
(dp.bids||[]).forEach(x=>{const w=(Math.log(1+x[1])/Math.log(1+(mx||1))*100).toFixed(0);
dh+='<div style="background:linear-gradient(90deg,rgba(34,197,94,.25) '+w+'%,transparent '+w+'%)">BUY &nbsp;'+x[0]+' ('+x[1]+')</div>';});
if(dp.asks&&dp.asks.length&&dp.bids&&dp.bids.length){var ba=dp.asks[dp.asks.length-1][0],bb=dp.bids[0][0];dh='<div style="color:#8b5cf6;font-weight:700">SPREAD '+(ba-bb).toFixed(1)+' | MID '+((ba+bb)/2).toFixed(1)+'</div>'+dh;}document.getElementById('dom').innerHTML=dh||'…';

window.__minUSD=window.__minUSD||25000;let ph='';(d.prints||[]).slice().reverse().forEach(x=>{if(x.usd<window.__minUSD)return;const c=x.sell?'#ef4444':'#22c55e';ph+='<div style="color:'+c+'">'+(x.sell?'SELL':'BUY')+' '+x.p+' \u00d7 '+x.q+' = $'+x.usd+'</div>';});document.getElementById('pr').innerHTML=ph||'is filter me koi trade nahi';draw(d);}catch(e){}}
function draw(d){drawChart(d);drawEq(d);}
function drawEq(d){const svg=document.getElementById('eq');const r=d.equity_curve||[];if(!svg||!r.length){if(svg)svg.innerHTML='<text x="10" y="60" fill="#8a8a8a" font-size="13">abhi koi band trade nahi - pehli trade ka intezar</text>';return;}
const W=svg.clientWidth||700,H=120;svg.setAttribute('viewBox','0 0 '+W+' '+H);
let hi=Math.max.apply(null,r),lo=Math.min.apply(null,r);if(hi===lo){hi+=1;lo-=1;}
const X=i=>10+i*(W-20)/Math.max(1,r.length-1),Y=p=>H-8-(p-lo)/(hi-lo)*(H-16);
let pts=r.map((p,i)=>X(i)+','+Y(p)).join(' ');
const up=r[r.length-1]>=10000,col=up?'#22c55e':'#ef4444';
svg.innerHTML='<polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="2"/>'+
'<line x1="0" y1="'+Y(10000)+'" x2="'+W+'" y2="'+Y(10000)+'" stroke="#8a8a8a" stroke-dasharray="4,4"/>';}
function drawChart(d){const svg=document.getElementById('ch');const cs=d.candles||[];if(!cs.length){return;}
const W=svg.clientWidth||700,H=230;svg.setAttribute('viewBox','0 0 '+W+' '+H);
let hi=-1e18,lo=1e18,mv=0;cs.forEach(c=>{hi=Math.max(hi,c.h);lo=Math.min(lo,c.l);mv=Math.max(mv,c.v||0);});
if(d.signal){hi=Math.max(hi,d.signal.target);lo=Math.min(lo,d.signal.stop);}
const pad=(hi-lo)*0.1||1;hi+=pad;lo-=pad;
const X=i=>10+i*(W-20)/cs.length, Y=p=>H-10-(p-lo)/(hi-lo)*(H-20);
let s='';cs.forEach((c,i)=>{const up=c.c>=c.o,col=up?'#22c55e':'#ef4444',x=X(i),w=Math.max(2,(W-20)/cs.length-3);
s+='<line x1="'+x+'" y1="'+Y(c.h)+'" x2="'+x+'" y2="'+Y(c.l)+'" stroke="'+col+'" stroke-width="1"/>';
s+='<rect x="'+(x-w/2)+'" y="'+Y(Math.max(c.o,c.c))+'" width="'+w+'" height="'+Math.max(2,Math.abs(Y(c.o)-Y(c.c)))+'" fill="'+col+'"/>';
const vh=(c.v||0)/(mv||1)*34;
s+='<rect x="'+(x-w/2)+'" y="'+(H-4-vh)+'" width="'+w+'" height="'+vh+'" fill="'+col+'" opacity="0.45"/>';});
if(d.signal){const g=d.signal;
s+='<line x1="0" y1="'+Y(g.target)+'" x2="'+W+'" y2="'+Y(g.target)+'" stroke="#22c55e" stroke-dasharray="5,4"/>';
s+='<line x1="0" y1="'+Y(g.stop)+'" x2="'+W+'" y2="'+Y(g.stop)+'" stroke="#ef4444" stroke-dasharray="5,4"/>';
s+='<circle cx="'+(W-14)+'" cy="'+Y(g.entry)+'" r="5" fill="'+(g.side==='long'?'#22c55e':'#ef4444')+'"/>';}
if(d.price){s+='<line x1="0" y1="'+Y(d.price)+'" x2="'+W+'" y2="'+Y(d.price)+'" stroke="#f7f7f7" stroke-dasharray="2,3" opacity="0.7"/>';}svg.innerHTML=s;}
async function setTF(tf){await fetch('/api/chart?tf='+tf);document.querySelectorAll('.tf').forEach(e=>e.classList.toggle('on',e.dataset.tf===tf));t();} document.getElementById('f25').onclick=()=>{window.__minUSD=25000;document.getElementById('f25').style.background='#8b5cf6';document.getElementById('f100').style.background='rgba(255,255,255,.08)';t();};document.getElementById('f100').onclick=()=>{window.__minUSD=100000;document.getElementById('f100').style.background='#8b5cf6';document.getElementById('f25').style.background='rgba(255,255,255,.08)';t();};setInterval(t,3000);t();
let RP={on:false,i:0,data:[],timer:null};
document.getElementById('rplay').onclick=async()=>{
if(RP.on){clearInterval(RP.timer);RP.on=false;document.getElementById('rplay').textContent='Play';return;}
const tf=document.getElementById('rtf').value;
const r=await (await fetch('/api/history?tf='+tf,{cache:'no-store'})).json();
if(!r.ok){document.getElementById('rinfo').textContent='history nahi mili';return;}
RP={on:true,i:60,data:r.candles,timer:null};
document.getElementById('rplay').textContent='Pause';
document.getElementById('rinfo').textContent=r.count+' candles ('+tf+')';
RP.timer=setInterval(()=>{if(RP.i>=RP.data.length){clearInterval(RP.timer);RP.on=false;document.getElementById('rplay').textContent='Play';return;}
RP.i++;document.getElementById('rinfo').textContent='candle '+RP.i+'/'+RP.data.length+' ('+tf+')';
drawChart({candles:RP.data.slice(Math.max(0,RP.i-60),RP.i),signal:null});},300);};
document.getElementById('rlive').onclick=()=>{if(RP.on){clearInterval(RP.timer);RP.on=false;}document.getElementById('rplay').textContent='Play';document.getElementById('rinfo').textContent='live wapas';t();};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def _json(self, obj: dict, code: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/state":
            self._json(STATE)
        elif self.path.startswith("/api/chart"):
            from urllib.parse import urlparse, parse_qs  # chart TF switch
            global CHART_TF
            tf = parse_qs(urlparse(self.path).query).get("tf", ["5m"])[0]
            if tf not in ALL_TF:
                self._json({"ok": False, "error": "galat timeframe"}, 400)
                return
            CHART_TF = tf
            _note(f"chart TF: {tf}")
            self._json({"ok": True, "chart_tf": CHART_TF})
        elif self.path.startswith("/api/history"):
            from urllib.parse import urlparse, parse_qs  # replay: file se pichli candles
            tf = parse_qs(urlparse(self.path).query).get("tf", ["5m"])[0]
            if tf not in ALL_TF:
                self._json({"ok": False, "error": "galat timeframe"}, 400)
                return
            try:
                rows = json.loads((Path(__file__).resolve().parents[2] / "data" / f"BTCUSDT_{tf}.json").read_text())
                rows = rows[-500:]
                self._json({"ok": True, "tf": tf, "count": len(rows),
                            "candles": [{"t": r[0], "o": float(r[1]), "h": float(r[2]),
                                         "l": float(r[3]), "c": float(r[4]), "v": float(r[5])} for r in rows]})
            except Exception as e:
                self._json({"ok": False, "error": str(e)[:150]}, 500)
        elif self.path == "/health":
            self._json({"ok": STATE["ok"], "updated_at": STATE["updated_at"]})
        elif self.path in ("/", "/index.html"):
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"ok": False, "error": "nahi mila"}, 404)


PORT = 8091  # 8090 system ke aur software ne pakda hua hai

if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    print(f"Dashboard: http://127.0.0.1:{PORT}", flush=True)
    try:
        HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except OSError:
        print(f"PORT {PORT} busy hai - purana server band karo ya PORT badlo", flush=True)
        raise SystemExit(1)
