"""Dashboard server — DeepCharts look, stdlib only (koi install nahi).

Kaam: background me market → HTF rukh → LTF signal → paper, har 20 sec.
Screen: http://localhost:8090 (3-sec auto-refresh).
Design: Dashboard design.md (LOCKED). Skills: dashboard-builder + frontend-patterns.
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.signal import find_liquidity, find_zones, generate_signal, htf_bias, pullback_pct  # noqa: E402
from market.binance import Candle, fetch_klines  # noqa: E402
from market.validator import validate_candles  # noqa: E402
from paper.journal import Engine  # noqa: E402

SYMBOL = "BTCUSDT"
LTF, HTF = "5m", "1h"
BIAS_TF = {"1m": "5m", "3m": "15m", "5m": "1h", "15m": "1h", "30m": "1h",
           "1h": "4h", "2h": "4h", "4h": "1d", "6h": "1d", "8h": "1d", "12h": "1d", "1d": None}
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
        if bias == "WAIT":  # multi-TF fallback: 1h chup to 30m se rukh lo
            try:
                mtf = fetch_klines(SYMBOL, "30m", 120)[:-1]
                bias = htf_bias(mtf, len(mtf) - 1)
                if bias != "WAIT":
                    _note("rukh 30m fallback se")
            except Exception:
                pass
        STATE["bias"] = bias
        STATE["price"] = ltf[-1].close
        if LAST_CLOSED.get(LTF) != ltf[-1].time:  # nayi band candle
            LAST_CLOSED[LTF] = ltf[-1].time
            pb = pullback_pct(htf, len(htf) - 1)
            sig = generate_signal(ltf, len(ltf) - 1, bias=bias)
            if sig:
                ENGINE.queue(sig, LTF)
                STATE["signal"] = {"side": sig.side, "entry": sig.entry, "stop": sig.stop,
                                   "target": sig.target, "rr": round(sig.rr, 2),
                                   "event": sig.event, "reason": sig.reason,
                                   "zone_kind": sig.zone_kind, "zone_high": sig.zone_high,
                                   "zone_low": sig.zone_low, "sweep_price": sig.sweep_price}
                _note(f"signal {sig.side} {sig.event} RR {sig.rr:.1f}")
            else:
                STATE["signal"] = None
                _note(f"scan: rukh {bias}, koi entry nahi")
        ENGINE.on_candle(LTF, ltf[-1], TF_MS[LTF])
        closed_trades = []
        eq = 0.0
        run = []
        for t in ENGINE.closed[-100:]:
            eq += t.pnl
            run.append(round(eq, 2))
            closed_trades.append({
                "id": t.id,
                "side": t.side,
                "timeframe": t.timeframe,
                "entry": t.entry,
                "stop": t.stop,
                "target": t.target,
                "exit": t.exit,
                "exit_reason": t.exit_reason,
                "r_multiple": round(t.r_multiple, 2),
                "opened_at": t.opened_at,
                "closed_at": t.closed_at,
                "entry_time": t.signal_time,
            })
        STATE["closed_trades"] = closed_trades[-20:]
        STATE["equity_curve"] = run
        STATE["paper"] = ENGINE.summary()
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
                                   "usd": round(usd), "sell": bool(t["m"]),
                                   "t": int(t["T"])})
            STATE["prints"] = prints[-15:]
        except Exception:
            pass
        STATE["candles"] = [{"t": c.time, "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume}
                            for c in chart_candles[-60:]]  # chart TF ki aakhri 60 band candles
        STATE["chart_tf"] = CHART_TF
        btf = BIAS_TF.get(CHART_TF)
        bcs = {"5m": ltf, "1h": htf}.get(btf) if btf else None
        if btf and bcs is None:
            bcs = fetch_klines(SYMBOL, btf, 120)[:-1]
        cbias = htf_bias(bcs, len(bcs) - 1) if bcs else "BOTH"
        marks = []
        try:  # history-deep ICT: file se chart TF ki pichli ~400 candles (live+history dono par)
            frows = json.loads((Path(__file__).resolve().parents[2] / "data" / f"BTCUSDT_{CHART_TF}.json").read_text())
            hist = [Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]),
                           close=float(r[4]), volume=float(r[5])) for r in frows[-400:]]
        except Exception:
            hist = chart_candles
        for j in range(40, len(hist)):
            gs = generate_signal(hist[: j + 1], j, bias=cbias)
            if gs and len(marks) < 30:
                marks.append({"t": hist[j].time, "k": j - (len(hist) - 60), "side": gs.side,
                              "entry": gs.entry, "zone_kind": gs.zone_kind,
                              "zone_high": gs.zone_high, "zone_low": gs.zone_low})
        STATE["chart_signals"] = [m for m in marks if m["k"] >= -400]
        STATE["chart_bias"] = cbias
        try:
            STATE["zones"] = find_zones(hist, len(hist) - 1, min(400, max(60, len(hist) - 2)))
            STATE["pools"] = find_liquidity(hist, len(hist) - 1)
        except Exception:
            STATE["zones"] = []
            STATE["pools"] = []
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
.note{margin-top:8px;color:#6a6a72;font-size:12px}.tf{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);color:#a8a8a8;padding:3px 10px;border-radius:20px;font-size:12px;cursor:pointer}.tf.on{background:#8b5cf6;color:#fff;border-color:#8b5cf6;font-weight:700}#chartcard.fs{position:fixed;inset:8px;z-index:50;overflow:auto;background:#030303}#chartcard.fs #ch{height:75vh !important}body.light{background:#ffffff;color:#131722}body.light .bar,body.light .engine,body.light .card,body.light .pnl{background:#f5f6f8 !important;border-color:#e0e3eb !important;color:#131722}body.light .chart{background:#ffffff !important}body.light .note,body.light .pnl .k,body.light .chart h3{color:#787b86 !important}body.light .tf{background:#eef0f3 !important;color:#555761 !important;border-color:#e0e3eb !important}#p,.big,.pr,.cell{font-family:'JetBrains Mono',Consolas,monospace}.card{transition:border-color .15s ease-out,transform .15s ease-out}button{transition:background .15s ease-out;cursor:pointer}button:hover{filter:brightness(1.2)}.tf{transition:background .15s ease-out}</style></head><body>
<div class="bar"><span class="logo">FIVE MARK V1</span><span class="sym">BTCUSDT</span><span class="tf" data-tf="1m" onclick="setTF('1m')">1m</span><span class="tf on" data-tf="5m" onclick="setTF('5m')">5m</span><span class="tf" data-tf="15m" onclick="setTF('15m')">15m</span><span class="tf" data-tf="1h" onclick="setTF('1h')">1h</span><span class="tf" data-tf="4h" onclick="setTF('4h')">4h</span><span class="tf" data-tf="1d" onclick="setTF('1d')">1d</span>
<span class="pr" id="p">…</span><span id="cd" style="color:#8b5cf6;font-size:13px">--:--</span><span class="st" id="s">…</span></div>
<div class="eng" id="e">ENGINE: load ho raha hai…</div>
<div class="grid">
<div class="card"><h3>HTF RUKH (1h)</h3><div class="big" id="b">…</div></div>
<div class="card"><h3>SIGNAL (5m)</h3><div class="big" id="g">…</div></div>
<div class="card"><h3>PAPER ($10k)</h3><div class="big" id="w">…</div></div>
<div class="card"><h3>STRATEGY (90D jaisa)</h3><div class="big" id="st">…</div></div>
</div>
<div class="grid"><div class="card"><h3>12 TIMEFRAMES — LIVE (hara=OK)</h3><div id="tf" style="display:grid;grid-template-columns:repeat(6,1fr);gap:4px;font-size:12px"></div></div></div>
<div class="grid"><div class="card"><h3>P&L CURVE (CUMULATIVE)</h3><svg id="eq" width="100%" height="120"></svg></div></div>
<div class="grid"><div class="card" id="chartcard"><h3 id="chh">CHART — 5m (LIVE)</h3><div style="margin:6px 0;font-size:12px;display:flex;gap:6px"><button id="dt" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">Trendline</button><button id="dh" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">H-Line</button><button id="dc" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">Clear</button><button id="dth" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">☀ Light</button><button id="df" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">⛶ Full</button><button id="dgo" style="background:#8b5cf6;color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">⦿ LIVE</button><span id="dmsg" style="color:#8b5cf6"></span></div><div style="margin:0 0 6px;font-size:12px;display:flex;gap:6px;flex-wrap:wrap"><span style="color:#8a8a8a;align-self:center">LAYERS</span><button id="L_fp" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">FP</button><button id="L_delta" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">Delta</button><button id="L_vol" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">Vol</button><button id="L_liq" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">Liq</button><button id="L_tr" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">Trades</button><button id="L_dom" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">DOM</button><button id="L_prof" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">Prof</button><button id="L_lv" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px">Levels</button></div><div style="position:relative"><canvas id="ch" style="width:100%;height:260px;cursor:crosshair;display:block"></canvas><div id="chTip" style="position:absolute;display:none;background:#1E222D;color:#E0E3EB;font-size:11px;padding:4px 8px;border-radius:4px;pointer-events:none;z-index:20;border:1px solid rgba(255,255,255,.12);font-family:monospace;white-space:pre"></div></div></div></div>
<div class="grid"><div class="card"><h3>REPLAY (practice, pichla data)</h3>
<div style="font-size:13px;display:flex;gap:8px;align-items:center">
<select id="rtf"><option>5m</option><option>15m</option><option>1h</option><option>4h</option><option>1d</option></select>
<button id="rplay" style="background:#8b5cf6;color:#fff;border:none;padding:4px 14px;border-radius:14px;font-weight:700">Play</button>
<button id="rlive" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:4px 14px;border-radius:14px">Live</button>
<span id="rinfo" style="color:#8a8a8a"></span></div></div></div>
<div class="grid"><div class="card"><h3>BIG TRADES <button id="f25" style="background:#8b5cf6;color:#fff;border:none;padding:2px 10px;border-radius:10px;font-size:11px">$25k+</button> <button id="f100" style="background:rgba(255,255,255,.08);color:#fff;border:1px solid rgba(255,255,255,.15);padding:2px 10px;border-radius:10px;font-size:11px">$100k+</button></h3><div id="pr" style="font-size:12px;line-height:1.8"></div></div></div>
<div class="grid"><div class="card"><h3>DOM — ASLI LIQUIDITY (bids/asks)</h3><div id="dom" style="font-size:12px;line-height:1.8"></div></div></div>
<div class="grid"><div class="card"><h3>LINKED TFs — click to jump</h3><div id="strip" style="display:flex;gap:8px"></div></div></div>
<div class="grid"><div class="card"><h3>LOG (taza pehle)</h3><div class="log" id="l">…</div></div></div>
<p class="note">Live dashboard — 3-sec refresh. Design: Dashboard design.md (LOCKED).</p>
<script>
async function t(){try{const r=await fetch('/api/state',{cache:'no-store'});const d=await r.json();
document.getElementById('p').textContent=d.price||'…';
document.getElementById('s').innerHTML=d.ok?'<span class=ok>● DATA OK</span>':'<span class=bad>● '+d.error+'</span>';
document.getElementById('b').textContent=d.bias||'…';
document.getElementById('g').textContent=d.signal?(d.signal.side+' '+d.signal.event+' RR '+d.signal.rr):'koi entry nahi';
document.getElementById('w').textContent=d.paper.equity?('$'+d.paper.equity+' | '+d.paper.closed+' trades'):'…';
document.getElementById('st').textContent=(d.paper&&d.paper.closed!=null)?('Trades '+d.paper.closed+' | Win '+d.paper.win_rate+'% | Avg R:R '+d.paper.avg_r):'…';
document.getElementById('chh').textContent='CHART — '+(d.chart_tf||'5m')+((window.__LIVE!==false&&((window.__V||{off:0}).off||0)===0)?' (LIVE)':' (HELD)');document.getElementById('e').textContent='ENGINE: rukh '+d.bias+' | open '+((d.paper||{}).open||0)+' | '+(d.signal?('signal '+d.signal.side):'scan chal raha');
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
function drawChart(d){
window.__D=d;
const cv=document.getElementById('ch'),cs=d.candles||[];
if(!cs.length){return;}
const DPR=window.devicePixelRatio||1;
const VW=cv.clientWidth||700,VH=cv.clientHeight||260;
cv.width=VW*DPR;cv.height=VH*DPR;
const ctx=cv.getContext('2d');ctx.setTransform(DPR,0,0,DPR,0,0);
const L=document.body.classList.contains('light');
const C={bg:L?'#ffffff':'#030303',grid:L?'#e0e3eb':'rgba(255,255,255,0.09)',
txt:L?'#787b86':'#8a8a8a',up:L?'#089981':'#22c55e',dn:L?'#F23645':'#ef4444',
purple:'#8b5cf6',yellow:'#f5b301',blue:'#2962FF',fg:L?'#131722':'#e6e6e6'};
ctx.fillStyle=C.bg;ctx.fillRect(0,0,VW,VH);
// view state (zoom/pan)
const V=window.__V=window.__V||{off:0,zoom:1};
const N=cs.length,visN=Math.max(10,Math.floor(N/V.zoom));
V.off=Math.max(0,Math.min(Math.max(0,N-visN),V.off||0));
let endI=N-1-V.off;if(endI>N-1)endI=N-1;if(endI<visN-1)endI=visN-1;
let startI=endI-visN+1;if(startI<0){startI=0;endI=Math.min(N-1,visN-1);}
const vis=cs.slice(startI,endI+1);
let hi=-1e18,lo=1e18,mv=0;vis.forEach(c=>{hi=Math.max(hi,c.h);lo=Math.min(lo,c.l);mv=Math.max(mv,c.v||0);});
if(d.signal){hi=Math.max(hi,d.signal.target);lo=Math.min(lo,d.signal.stop);}
const pad=(hi-lo)*0.1||1;hi+=pad;lo-=pad;
const LAY=window.__LAY||{vol:1,prof:1,lv:1};
const domW=(LAY.dom&&d.depth&&(d.depth.bids||[]).length)?64:0;
const PW=VW-70-domW,PH=VH-50;
const X=i=>10+i*(PW/Math.max(1,vis.length)), Y=p=>VH-30-(p-lo)/(hi-lo)*(PH);
window.__MAP={lo:lo,hi:hi,W:VW,H:VH,startI:startI};window.__VIS=vis;
// grid + price axis
ctx.font='10px Inter,Arial';ctx.textBaseline='middle';
for(let k=0;k<=4;k++){const py=10+k*(PH)/4,pv=(hi-(hi-lo)*k/4).toFixed(1);
ctx.strokeStyle=C.grid;ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(10,py);ctx.lineTo(VW-60,py);ctx.stroke();ctx.setLineDash([]);
ctx.fillStyle=C.txt;ctx.fillText(pv,VW-58,py);}
// time axis
const step=Math.ceil(vis.length/6);
ctx.fillStyle=C.txt;
for(let i=0;i<vis.length;i+=step){const dt=new Date(vis[i].t);
const hh=String(dt.getHours()).padStart(2,'0'),mm=String(dt.getMinutes()).padStart(2,'0');
ctx.fillText(hh+':'+mm,X(i)-12,VH-12);}
// candles + volume
(function(){const SH=h=>{const hh=new Date(h).getUTCHours();return hh<7?0:(hh<12?1:(hh<21?2:0));};
const SC=['rgba(41,98,255,0.05)','rgba(139,92,246,0.06)','rgba(34,197,94,0.05)'];
vis.forEach((c,i)=>{const x=X(i),w=Math.max(2,PW/vis.length-1);
ctx.fillStyle=SC[SH(c.t)];ctx.fillRect(x-w/2,0,w,VH-30);});})();
if(LAY.prof)(function(){const ROWS=22,bins=new Array(ROWS).fill(0);let mx=0;
vis.forEach(c=>{const b=Math.min(ROWS-1,Math.max(0,Math.floor((hi-c.c)/(hi-lo||1)*ROWS)));bins[b]+=(c.v||0);mx=Math.max(mx,bins[b]);});
ctx.fillStyle='rgba(41,98,255,0.30)';
bins.forEach((v,r)=>{const w2=(v/(mx||1))*52;const y=10+r*(VH-50)/ROWS;
ctx.fillRect(VW-62-domW,y,w2,Math.max(1,(VH-50)/ROWS-1));});})();
vis.forEach((c,i)=>{const up=c.c>=c.o,col=up?C.up:C.dn,x=X(i),w=Math.max(2,PW/vis.length-3);
ctx.strokeStyle=col;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,Y(c.h));ctx.lineTo(x,Y(c.l));ctx.stroke();
const yO=Y(c.o),yC=Y(c.c);ctx.fillStyle=col;
ctx.fillRect(x-w/2,Math.min(yO,yC),w,Math.max(2,Math.abs(yO-yC)));
if(LAY.vol){const vh=(c.v||0)/(mv||1)*34;ctx.globalAlpha=0.45;
ctx.fillRect(x-w/2,VH-4-vh,w,vh);ctx.globalAlpha=1;}});
// OHLC legend + SELL/BUY
const _lc=vis[vis.length-1];
ctx.fillStyle=C.fg;ctx.font='700 12px Inter,Arial';
ctx.fillText('O '+_lc.o+' H '+_lc.h+' L '+_lc.l+' C '+_lc.c,12,14);
ctx.strokeStyle='#F23645';ctx.strokeRect(12,22,64,20);
ctx.fillStyle='#F23645';ctx.font='700 11px Inter,Arial';ctx.fillText('SELL',16,36);
ctx.strokeStyle=C.blue;ctx.strokeRect(80,22,64,20);
ctx.fillStyle=C.blue;ctx.fillText('BUY',84,36);
// past strategy markers (time-anchored: live+history dono par sahi jagah)
var t2i={};vis.forEach((c,i)=>{t2i[c.t]=i;});
if(LAY.lv)(d.chart_signals||[]).forEach(m=>{const vi=(m.t!=null&&t2i[m.t]!=null)?t2i[m.t]:m.k-startI;if(vi<0||vi>=vis.length)return;
const mx=X(vi),mc=m.side==='long'?C.up:C.dn;
ctx.fillStyle=mc;ctx.beginPath();ctx.moveTo(mx,Y(m.entry)-14);ctx.lineTo(mx-5,Y(m.entry)-6);ctx.lineTo(mx+5,Y(m.entry)-6);ctx.closePath();ctx.fill();});
// live signal: zone + sweep + entry/stop/target
if(d.signal){const g=d.signal;
if(g.zone_high){ctx.fillStyle=g.side==='long'?'rgba(34,197,94,0.15)':'rgba(239,68,68,0.15)';
ctx.fillRect(10,Y(g.zone_high),PW,Math.max(4,Math.abs(Y(g.zone_low)-Y(g.zone_high))));
ctx.fillStyle=C.purple;ctx.font='700 11px Inter,Arial';ctx.fillText(g.zone_kind+' ZONE',14,Y(g.zone_high)+13);}
if(g.sweep_price){ctx.strokeStyle=C.yellow;ctx.lineWidth=2;ctx.beginPath();ctx.arc(VW/2,Y(g.sweep_price),5,0,7);ctx.stroke();
ctx.fillStyle=C.yellow;ctx.font='11px Inter,Arial';ctx.fillText('SWEEP',VW/2+8,Y(g.sweep_price)+4);}
ctx.setLineDash([5,4]);ctx.strokeStyle=C.up;ctx.beginPath();ctx.moveTo(0,Y(g.target));ctx.lineTo(VW,Y(g.target));ctx.stroke();
ctx.strokeStyle=C.dn;ctx.beginPath();ctx.moveTo(0,Y(g.stop));ctx.lineTo(VW,Y(g.stop));ctx.stroke();ctx.setLineDash([]);
ctx.fillStyle=g.side==='long'?C.up:C.dn;ctx.beginPath();ctx.arc(VW-14,Y(g.entry),5,0,7);ctx.fill();}
// live price line + tag
if(d.price){const cc=d.price>=_lc.o?C.up:C.dn;
ctx.setLineDash([2,3]);ctx.strokeStyle=cc;ctx.beginPath();ctx.moveTo(0,Y(d.price));ctx.lineTo(VW,Y(d.price));ctx.stroke();ctx.setLineDash([]);
ctx.fillStyle=cc;const pt=String(d.price);ctx.fillRect(VW-58,Y(d.price)-9,56,18);
ctx.fillStyle=L?'#fff':'#030303';ctx.font='700 11px Inter,Arial';ctx.fillText(pt,VW-56,Y(d.price)+4);}
// user drawings
if(LAY.lv)(d.zones||[]).forEach(z=>{const zc=z.status==='breaker'?'rgba(245,179,1,0.25)':(z.status==='mitigated'?(z.side==='long'?'rgba(34,197,94,0.12)':'rgba(239,68,68,0.12)'):'rgba(139,92,246,0.12)');
ctx.fillStyle=zc;ctx.fillRect(10,Y(z.high),VW-70,Math.max(3,Math.abs(Y(z.low)-Y(z.high))));});
if(LAY.lv)(d.pools||[]).forEach(o=>{ctx.strokeStyle='#f5b301';ctx.setLineDash([6,4]);ctx.globalAlpha=0.8;ctx.beginPath();ctx.moveTo(10,Y(o.price));ctx.lineTo(VW-60,Y(o.price));ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;
ctx.fillStyle='#f5b301';ctx.font='700 10px Inter,Arial';ctx.fillText(o.side+' x'+o.count,VW-150,Y(o.price)-5);});
drawUser(vis,X,Y,VW,VH);
drawClosedTrades(d, vis, X, Y, VW, VH, lo, hi);
// ---- FIVE MARKET order-flow layers (sab real data; fake kuch nahi) ----
ensureFP(vis);
(function(){ // FOOTPRINT: bid x ask per price-step (zoom par hi, vis<=40)
if(!LAY.fp||vis.length>40)return;
var slotW=PW/Math.max(1,vis.length),tf=(window.__CHTF)||'5m';
vis.forEach(function(c,i){
var k=tf+':'+c.t,fp=window.__FP[k],x=X(i);
if(!fp||!fp.ok||!fp.rows||!fp.rows.length){
ctx.fillStyle='#5a5a5a';ctx.font='8px Inter,Arial';
ctx.fillText(fp&&fp.err?'NO DATA':'…',x-8,Y(c.c));return;}
var mx=0.0001;fp.rows.forEach(function(r){mx=Math.max(mx,r.tot);});
var st=fp.step||1;
fp.rows.forEach(function(r){
var y1=Y(r.p),y0=Y(r.p+st),h=Math.max(1,y1-y0);
var cx=x,wb=(r.bid/mx)*(slotW/2-1),wa=(r.ask/mx)*(slotW/2-1);
ctx.fillStyle='rgba(239,68,68,0.75)';ctx.fillRect(cx-wb,y0,wb,h);
ctx.fillStyle='rgba(34,197,94,0.75)';ctx.fillRect(cx,y0,wa,h);
if(r.ask>=3*Math.max(r.bid,0.0001)||r.bid>=3*Math.max(r.ask,0.0001)){ctx.strokeStyle='#f5b301';ctx.lineWidth=1;ctx.strokeRect(cx-wb,y0,wb+wa,h);}});
if(slotW>=54){var dlt=0;fp.rows.forEach(function(r){dlt+=r.delta;});
ctx.fillStyle=dlt>=0?'#22c55e':'#ef4444';ctx.font='700 8px Inter,Arial';
ctx.fillText((dlt>=0?'+':'')+dlt.toFixed(2),x-slotW/2+2,VH-16);}
});})();
(function(){ // DELTA histogram (footprint data se; nahi to honest badge)
if(!LAY.delta)return;
var tf=(window.__CHTF)||'5m',ds=[],mx=0.0001,any=false;
vis.forEach(function(c){var fp=window.__FP[tf+':'+c.t],dlt=null;
if(fp&&fp.ok&&fp.rows){dlt=0;fp.rows.forEach(function(r){dlt+=r.delta;});any=true;}
ds.push(dlt);if(dlt!=null)mx=Math.max(mx,Math.abs(dlt));});
if(!any){ctx.fillStyle='rgba(0,0,0,0.55)';ctx.fillRect(VW/2-96,14,192,18);
ctx.strokeStyle='rgba(255,255,255,.15)';ctx.strokeRect(VW/2-96,14,192,18);
ctx.fillStyle='#8a8a8a';ctx.font='700 10px Inter,Arial';
ctx.fillText('DELTA — DATA UNAVAILABLE',VW/2-88,27);return;}
var bw=Math.max(2,PW/vis.length-2);
ds.forEach(function(dlt,i){if(dlt==null)return;
var h=Math.abs(dlt)/mx*24,x=X(i)-bw/2;
ctx.fillStyle=dlt>=0?'rgba(34,197,94,0.8)':'rgba(239,68,68,0.8)';
ctx.fillRect(x,VH-8-h,bw,Math.max(1,h));});})();
(function(){ // LIQUIDITY: depth history store nahi hoti — fake heatmap nahi, honest badge
if(!LAY.liq)return;
ctx.fillStyle='rgba(0,0,0,0.55)';ctx.fillRect(VW/2-170,34,340,20);
ctx.strokeStyle='rgba(245,179,1,0.6)';ctx.strokeRect(VW/2-170,34,340,20);
ctx.fillStyle='#f5b301';ctx.font='700 10px Inter,Arial';
ctx.fillText('LIQUIDITY HISTORY — DATA UNAVAILABLE',VW/2-158,48);})();
window.__PRINTS=[];
(function(){ // DEEP TRADES: asli $25k+ prints, marker size = size
if(!LAY.tr||!d.prints||!d.prints.length)return;
d.prints.forEach(function(pr){
if(pr.t==null)return;
var bi=0,bd=1e18;vis.forEach(function(c,i){var dd=Math.abs(c.t-pr.t);if(dd<bd){bd=dd;bi=i;}});
if(bd>TFMS()*2)return;
var x=X(bi),y=Y(pr.p),r=3+Math.min(9,pr.usd/50000);
ctx.fillStyle=pr.sell?'#ef4444':'#22c55e';ctx.globalAlpha=0.9;
ctx.beginPath();ctx.arc(x,y,r,0,7);ctx.fill();ctx.globalAlpha=1;
ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.beginPath();ctx.arc(x,y,r,0,7);ctx.stroke();
window.__PRINTS.push({x:x,y:y,r:r,pr:pr});});})();
(function(){ // CHART DOM: live depth snapshot, chart ka hissa (price scale ke bagal me)
if(!domW||!d.depth)return;
var bids=d.depth.bids||[],asks=d.depth.asks||[],x0=VW-58-domW,mx=0.0001;
bids.concat(asks).forEach(function(l){mx=Math.max(mx,l[1]);});
ctx.font='8px Inter,Arial';
asks.slice().reverse().forEach(function(l){
var y=Y(l[0]);if(y<10||y>VH-30)return;
var w=(l[1]/mx)*(domW-6);
ctx.fillStyle='rgba(239,68,68,0.35)';ctx.fillRect(x0+domW-2-w,y-5,w,10);
ctx.fillStyle='#ef4444';ctx.fillText(String(l[0]),x0+1,y+3);});
bids.forEach(function(l){
var y=Y(l[0]);if(y<10||y>VH-30)return;
var w=(l[1]/mx)*(domW-6);
ctx.fillStyle='rgba(34,197,94,0.35)';ctx.fillRect(x0+domW-2-w,y-5,w,10);
ctx.fillStyle='#22c55e';ctx.fillText(String(l[0]),x0+1,y+3);});})();
// crosshair
const MH=window.__MH;
if(MH){ctx.strokeStyle=C.purple;ctx.globalAlpha=0.7;ctx.setLineDash([4,3]);
ctx.beginPath();ctx.moveTo(MH.x,0);ctx.lineTo(MH.x,VH);ctx.stroke();
ctx.beginPath();ctx.moveTo(0,MH.y);ctx.lineTo(VW,MH.y);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;}
}

function drawClosedTrades(d, vis, X, Y, W, H, lo, hi) {
    if (!d.closed_trades || !d.closed_trades.length) return;
    const cs = d.closed_trades;
    const N = cs.length;
    cs.forEach(t => {
        // Only draw if the trade time falls within the visible range
        const visStart = vis[0].t;
        const visEnd = vis[vis.length - 1].t;
        if (t.entry_time < visStart || t.entry_time > visEnd) return;

        const entryX = X(t.entry_time);
        const entryY = Y(t.entry);
        const stopY = Y(t.stop);
        const targetY = Y(t.target);
        const exitY = Y(t.exit);

        const col = t.side === 'long' ? '#22c55e' : '#ef4444';
        const exitCol = t.exit_reason === 'target' ? '#22c55e' : (t.exit_reason === 'stop' ? '#ef4444' : '#f5b301');

        // Entry point
        ctx.fillStyle = t.side === 'long' ? '#22c55e' : '#ef4444';
        ctx.beginPath();
        ctx.moveTo(entryX, entryY - 14);
        ctx.lineTo(entryX - 6, entryY - 6);
        ctx.lineTo(entryX + 6, entryY - 6);
        ctx.closePath();
        ctx.fill();

        // Entry line
        ctx.strokeStyle = t.side === 'long' ? '#22c55e' : '#ef4444';
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(10, entryY);
        ctx.lineTo(VW - 60, entryY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Stop line
        ctx.strokeStyle = '#ef4444';
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(10, stopY);
        ctx.lineTo(VW - 60, stopY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Target line
        ctx.strokeStyle = '#22c55e';
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(10, targetY);
        ctx.lineTo(VW - 60, targetY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Exit point
        if (t.exit && t.exit_reason !== 'time') {
            ctx.fillStyle = t.exit_reason === 'target' ? '#22c55e' : '#ef4444';
            ctx.beginPath();
            ctx.arc(X(t.closed_at), Y(t.exit), 4, 0, Math.PI * 2);
            ctx.fill();
        }

        // Trade ID label
        ctx.fillStyle = '#8a8a8a';
        ctx.font = '10px Inter,Arial';
        ctx.fillText(t.id, entryX, entryY - 20);
    });
}
window.__LAY=(function(){try{return Object.assign({fp:0,delta:0,vol:1,liq:0,tr:0,dom:0,prof:1,lv:1},JSON.parse(localStorage.getItem('fmv_layers')||'{}'));}catch(e){return {fp:0,delta:0,vol:1,liq:0,tr:0,dom:0,prof:1,lv:1};}})();
window.__FP=window.__FP||{};
window.syncLiveBtn=function(){var live=window.__LIVE!==false&&((window.__V||{off:0}).off||0)===0;var el=document.getElementById('dgo');if(el)el.style.background=live?'#8b5cf6':'rgba(255,255,255,.08)';var h=document.getElementById('chh');if(h){var tf=(window.__D&&window.__D.chart_tf)||(window.__CHTF)||'5m';h.textContent='CHART — '+tf+(live?' (LIVE)':' (HELD)');}};
function layPaint(){[['L_fp','fp'],['L_delta','delta'],['L_vol','vol'],['L_liq','liq'],['L_tr','tr'],['L_dom','dom'],['L_prof','prof'],['L_lv','lv']].forEach(function(p){var el=document.getElementById(p[0]);if(el)el.style.background=window.__LAY[p[1]]?'#8b5cf6':'rgba(255,255,255,.08)';});}
[['L_fp','fp'],['L_delta','delta'],['L_vol','vol'],['L_liq','liq'],['L_tr','tr'],['L_dom','dom'],['L_prof','prof'],['L_lv','lv']].forEach(function(p){var el=document.getElementById(p[0]);if(el)el.onclick=function(){window.__LAY[p[1]]=window.__LAY[p[1]]?0:1;try{localStorage.setItem('fmv_layers',JSON.stringify(window.__LAY));}catch(e){}layPaint();if(window.__D)drawChart(window.__D);};});
layPaint();
var dgoEl=document.getElementById('dgo');if(dgoEl)dgoEl.onclick=function(){var V=window.__V=window.__V||{off:0,zoom:1};V.off=0;window.__LIVE=true;syncLiveBtn();if(window.__D)drawChart(window.__D);};
syncLiveBtn();
function TFMS(){var m={'1m':60000,'3m':180000,'5m':300000,'15m':900000,'30m':1800000,'1h':3600000,'2h':7200000,'4h':14400000,'6h':21600000,'8h':28800000,'12h':43200000,'1d':86400000};return m[(window.__CHTF)||'5m']||300000;}
function fpStep(c){return Math.max(0.1,Math.round((c.h-c.l)/10*10)/10);}
function ensureFP(vis){
var LAY=window.__LAY||{};
if(!(LAY.fp||LAY.delta)||!vis||!vis.length||vis.length>40)return;
var tf=(window.__CHTF)||'5m',now=Date.now(),ms=TFMS(),n=0;
for(var vi=0;vi<vis.length;vi++){var c=vis[vi];
if(n>=4)break;
var k=tf+':'+c.t;
if(window.__FP[k]||c.t>now-ms)continue;
n++;window.__FP[k]={loading:1};
(function(kk,cc){fetch('/api/footprint?tf='+tf+'&t='+cc.t+'&step='+fpStep(cc),{cache:'no-store'}).then(function(r){return r.json();}).then(function(j){window.__FP[kk]=j;if(window.__D)requestDraw();}).catch(function(){window.__FP[kk]={ok:false,err:1};});})(k,c);}}
var chEl=document.getElementById('ch');
if(chEl){
chEl.onmousemove=function(ev){var r=chEl.getBoundingClientRect();
var mx=ev.clientX-r.left,my=ev.clientY-r.top;
window.__MH={x:mx,y:my};
var tip=document.getElementById('chTip'),M=window.__MAP,vis=window.__VIS;
if(tip&&M&&vis&&vis.length){var PW=M.W-70,bi=Math.round((mx-10)/(PW/Math.max(1,vis.length)));
if(bi<0)bi=0;if(bi>=vis.length)bi=vis.length-1;
var c=vis[bi],dt=new Date(c.t);
var hh=String(dt.getHours()).padStart(2,'0'),mm=String(dt.getMinutes()).padStart(2,'0');
tip.style.display='block';tip.style.left=(mx+14)+'px';tip.style.top=(my+10)+'px';
var chh=c.c>=c.o,cc=chh?'#22c55e':'#ef4444';
tip.innerHTML='<b>'+hh+':'+mm+'</b> O '+c.o+' H '+c.h+' L '+c.l+' C <b style="color:'+cc+'">'+c.c+'</b> V '+c.v;}
if(window.__D)drawChart(window.__D);};
chEl.onmouseleave=function(){window.__MH=null;var tip=document.getElementById('chTip');if(tip)tip.style.display='none';if(window.__D)drawChart(window.__D);};
chEl.addEventListener('wheel',function(ev){ev.preventDefault();
var V=window.__V=window.__V||{off:0,zoom:1};
if(ev.shiftKey||ev.ctrlKey||Math.abs(ev.deltaX)>Math.abs(ev.deltaY)){
var cv=document.getElementById('ch');var W=cv.clientWidth||700;
var vis=window.__VIS||[];var perPx=vis.length/((W-70)||630);
var eq=ev.shiftKey?ev.deltaY:ev.deltaX;
var step=Math.round(-eq/20*perPx);if(step===0)step=eq>0?-1:1;
var cs=window.__D?window.__D.candles||[]:[];
var visN=Math.max(10,Math.floor(cs.length/(V.zoom||1)));
var rpon=false;try{rpon=RP.on;}catch(e){}
V.off=Math.max(0,Math.min(Math.max(0,cs.length-visN),V.off+step));
if(V.off>0||step>0)window.__LIVE=false;
if(V.off===0&&step<0)window.__LIVE=true;
if(!rpon&&cs.length-visN-V.off<=0)loadMore();
if(window.__D)drawChart(window.__D);syncLiveBtn();
}else{
var f=ev.deltaY>0?1.15:0.87;V.zoom=Math.min(8,Math.max(1,V.zoom*f));if(window.__D)drawChart(window.__D);}},{passive:false});
chEl.addEventListener('dblclick',function(){window.__V={off:0,zoom:1};if(window.__D)drawChart(window.__D);});
var _pd=null;
window.__LIVE=true;
chEl.addEventListener('contextmenu',function(ev){ev.preventDefault();});
chEl.addEventListener('mousedown',function(ev){
if(window.__TOOL)return;
if(ev.button!==0&&ev.button!==2&&!ev.shiftKey&&ev.button!==1)return;
var V0=window.__V||{off:0,zoom:1};_pd={x:ev.clientX,off:V0.off,moved:false};ev.preventDefault();});
window.addEventListener('mousemove',function(ev){if(!_pd)return;
var cv=document.getElementById('ch');var W=cv.clientWidth||700;
var vis=window.__VIS||[];var perPx=vis.length/((W-70)||630);
var dOff=Math.round((ev.clientX-_pd.x)*perPx);
if(Math.abs(ev.clientX-_pd.x)>4)_pd.moved=true;
var V=window.__V=window.__V||{off:0,zoom:1};
var cs=window.__D?window.__D.candles||[]:[];
var visN=Math.max(10,Math.floor(cs.length/(V.zoom||1)));
var rpon=false;try{rpon=RP.on;}catch(e){}
var maxOff=Math.max(0,cs.length-visN);
if(maxOff<=0&&dOff<0){V.zoom=Math.min(8,(V.zoom||1)*1.25);visN=Math.max(10,Math.floor(cs.length/V.zoom));maxOff=Math.max(0,cs.length-visN);}
V.off=Math.max(0,Math.min(maxOff,_pd.off-dOff));
if(V.off>0||dOff<0)window.__LIVE=false;
if(V.off===0&&dOff>0)window.__LIVE=true;
if(!rpon&&window.__D&&cs.length-visN-V.off<=0)loadMore();
if(window.__D)drawChart(window.__D);syncLiveBtn();});
window.addEventListener('mouseup',function(){if(_pd&&_pd.moved)window.__PANNED=true;_pd=null;});
}
async function setTF(tf){window.__CHTF=tf;window.__EXTRA=[];window.__HEXH=false;window.__TFEPOCH=(window.__TFEPOCH||0)+1;window.__V={off:0,zoom:1};window.__LIVE=true;startWS(tf);await fetch('/api/chart?tf='+tf);document.querySelectorAll('.tf').forEach(e=>e.classList.toggle('on',e.dataset.tf===tf));t();} document.getElementById('f25').onclick=()=>{window.__minUSD=25000;document.getElementById('f25').style.background='#8b5cf6';document.getElementById('f100').style.background='rgba(255,255,255,.08)';t();};document.getElementById('f100').onclick=()=>{window.__minUSD=100000;document.getElementById('f100').style.background='#8b5cf6';document.getElementById('f25').style.background='rgba(255,255,255,.08)';t();};window.__D=null;window.__EXTRA=[];window.__HEXH=false;var _t0=t;async function loadMore(){if(window.__LOADING||window.__HEXH)return;const live=(window.__D&&window.__D.candles)||[];const first=(window.__EXTRA.length?window.__EXTRA[0]:live[0]);if(!first)return;window.__LOADING=true;var dm0=document.getElementById('dmsg');if(dm0)dm0.textContent='history load…';try{const tf=(window.__CHTF)||'5m';const ep=window.__TFEPOCH||0;const r=await (await fetch('/api/history?tf='+tf+'&before='+first.t,{cache:'no-store'})).json();if(ep!==(window.__TFEPOCH||0)||tf!==((window.__CHTF)||'5m')){window.__LOADING=false;return;}if(r.ok&&(r.candles||[]).length){const have=new Set(window.__EXTRA.map(c=>c.t));const fresh=r.candles.filter(c=>c.t<first.t&&!have.has(c.t));window.__EXTRA=fresh.concat(window.__EXTRA).slice(-1940);if((r.candles||[]).length<500)window.__HEXH=true;}else window.__HEXH=true;}catch(e){}window.__LOADING=false;var dm1=document.getElementById('dmsg');if(dm1&&dm1.textContent==='history load…')dm1.textContent='';t();}t=function(){_t0();fetch('/api/state',{cache:'no-store'}).then(r=>r.json()).then(d=>{try{if(RP.on)return;}catch(e){}if(d.chart_tf&&(window.__CHTF)&&d.chart_tf!==(window.__CHTF))return;var oldN=(window.__D&&window.__D.candles||[]).length;if(window.__EXTRA.length){const cut=d.candles.length?d.candles[0].t:0;window.__EXTRA=window.__EXTRA.filter(c=>c.t<cut);d.candles=window.__EXTRA.concat(d.candles).slice(-2000);}if(window.__LIVE!==false){var V0=window.__V=window.__V||{off:0,zoom:1};V0.off=0;}else if(d.candles.length>oldN){var V1=window.__V=window.__V||{off:0,zoom:1};V1.off+=(d.candles.length-oldN);}window.__D=d;drawChart(d);syncLiveBtn();if(!window.__EXTRA.length&&!window.__HEXH)loadMore();});};async function tick(){try{if(RP.on)return;}catch(e){}try{const r=await (await fetch('/api/tick',{cache:'no-store'})).json();if(!r.ok||!window.__D||!window.__D.candles||!window.__D.candles.length)return;const cs=window.__D.candles;let f=cs[cs.length-1];const tfm={'1m':1,'5m':5,'15m':15,'1h':60,'4h':240,'1d':1440};const tf=(window.__CHTF)||'5m',slot=Math.floor(r.t/(tfm[tf]*60000))*(tfm[tf]*60000);if(f.t===slot){f={t:f.t,o:f.o,h:Math.max(f.h,r.price),l:Math.min(f.l,r.price),c:r.price,v:f.v};}else{f={t:slot,o:f.c,h:r.price,l:r.price,c:r.price,v:0};cs.push(f);}window.__D.price=r.price;document.getElementById('p').textContent=r.price;drawChart(window.__D);}catch(e){}}window.__DRAW=[];try{window.__DRAW=JSON.parse(localStorage.getItem('fmv_draws')||'[]');}catch(e){window.__DRAW=[];}window.__TOOL='';function drawUser(cs,X,Y,W,H){
const cv=document.getElementById('ch'),ctx=cv.getContext('2d');
const ti=t=>{let bi=0;cs.forEach((c,i)=>{if(Math.abs(c.t-t)<Math.abs(cs[bi].t-t))bi=i;});return 10+bi*(W-70)/cs.length;};
(window.__DRAW||[]).forEach(d=>{if(d.k==='h'){ctx.strokeStyle='#8b5cf6';ctx.setLineDash([4,3]);ctx.beginPath();ctx.moveTo(10,Y(d.p));ctx.lineTo(W-60,Y(d.p));ctx.stroke();ctx.setLineDash([]);}
else{ctx.strokeStyle='#f5b301';ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(ti(d.t1),Y(d.p1));ctx.lineTo(ti(d.t2),Y(d.p2));ctx.stroke();ctx.lineWidth=1;}});}function saveDraw(){try{localStorage.setItem('fmv_draws',JSON.stringify(window.__DRAW));}catch(e){}}function markTool(id,msg){['dt','dh'].forEach(k=>document.getElementById(k).style.background='rgba(255,255,255,.08)');if(id)document.getElementById(id).style.background='#8b5cf6';document.getElementById('dmsg').textContent=msg||'';}document.getElementById('dt').onclick=()=>{window.__TOOL=window.__TOOL==='t'?'':'t';window.__T1=null;markTool(window.__TOOL?'dt':'','Trend: 2 click chart par');};document.getElementById('dh').onclick=()=>{window.__TOOL=window.__TOOL==='h'?'':'h';markTool(window.__TOOL?'dh':'','H-Line: 1 click');};document.getElementById('dc').onclick=()=>{window.__DRAW=[];saveDraw();markTool('','saaf!');t();};document.getElementById('ch').addEventListener('click',ev=>{if(window.__PANNED){window.__PANNED=false;return;}const svg0=document.getElementById('ch'),rr0=svg0.getBoundingClientRect(),qx0=ev.clientX-rr0.left,qy0=ev.clientY-rr0.top;var hitP=null;(window.__PRINTS||[]).forEach(function(m){if(Math.abs(m.x-qx0)<m.r+4&&Math.abs(m.y-qy0)<m.r+4)hitP=m;});if(hitP){var tipP=document.getElementById('chTip'),pp=hitP.pr,pdt=new Date(pp.t);tipP.style.display='block';tipP.style.left=(qx0+14)+'px';tipP.style.top=(qy0+10)+'px';tipP.innerHTML='<b>'+(pp.sell?'SELL':'BUY')+'</b> '+pp.p+'<br>qty '+pp.q+' = $'+pp.usd+'<br>'+String(pdt.getHours()).padStart(2,'0')+':'+String(pdt.getMinutes()).padStart(2,'0')+':'+String(pdt.getSeconds()).padStart(2,'0');setTimeout(function(){tipP.style.display='none';},4000);return;}if(!window.__TOOL||!window.__MAP)return;const svg=document.getElementById('ch'),r=svg.getBoundingClientRect();const sx=(ev.clientX-r.left),sy=(ev.clientY-r.top);const m=window.__MAP,vis2=window.__VIS||[];if(!vis2.length)return;const p=m.lo+(m.H-30-sy)/(m.H-50)*(m.hi-m.lo);let bi=0;vis2.forEach((c,i)=>{const x=10+i*(m.W-70)/vis2.length;if(Math.abs(x-sx)<Math.abs(10+bi*(m.W-70)/vis2.length-sx))bi=i;});const t0=vis2[bi].t;if(window.__TOOL==='h'){window.__DRAW.push({k:'h',p:p});saveDraw();markTool('','H-Line lag gayi');t();}else{if(!window.__T1){window.__T1={t:t0,p:p};markTool('dt','ab doosra click');}else{window.__DRAW.push({k:'t',t1:window.__T1.t,p1:window.__T1.p,t2:t0,p2:p});window.__T1=null;saveDraw();markTool('','Trendline lag gayi');t();}}});document.getElementById('df').onclick=()=>{const c=document.getElementById('chartcard');const on=c.classList.toggle('fs');const svg=document.getElementById('ch');if(on){svg.style.width='100%';svg.style.height=(window.innerHeight-170)+'px';}else{svg.style.width='';svg.style.height='';}document.getElementById('df').textContent=on?'✕ Band':'⛶ Full';t();};document.addEventListener('keydown',e=>{if(e.key==='Escape'){const c=document.getElementById('chartcard');if(c.classList.contains('fs')){c.classList.remove('fs');const svg2=document.getElementById('ch');svg2.style.width='';svg2.style.height='';document.getElementById('df').textContent='⛶ Full';t();}}});if(localStorage.getItem('fmv_theme')==='light'){document.body.classList.add('light');}document.getElementById('dth').onclick=()=>{const l=document.body.classList.toggle('light');try{localStorage.setItem('fmv_theme',l?'light':'dark');}catch(e){}document.getElementById('dth').textContent=l?'🌙 Dark':'☀ Light';t();};if(document.body.classList.contains('light'))document.getElementById('dth').textContent='🌙 Dark';setInterval(()=>{const tfm={'1m':1,'5m':5,'15m':15,'1h':60,'4h':240,'1d':1440};const tf=(window.__CHTF)||'5m',ms=tfm[tf]*60000,left=ms-(Date.now()%ms);const mm=String(Math.floor(left/60000)).padStart(2,'0'),ss=String(Math.floor(left%60000/1000)).padStart(2,'0');const el=document.getElementById('cd');if(el)el.textContent=mm+':'+ss;},1000);window.__WS=null;
function requestDraw(){if(window.__RAFP)return;window.__RAFP=1;requestAnimationFrame(function(){window.__RAFP=0;if(window.__D)drawChart(window.__D);});}
function startWS(tf){try{if(window.__WS)window.__WS.close();}catch(e){}
try{const ws=new WebSocket('wss://fstream.binance.com/ws/btcusdt@kline_'+tf);
window.__WS=ws;
ws.onmessage=function(ev){try{const m=JSON.parse(ev.data),k=m.k;if(!k||!window.__D||!window.__D.candles)return;
try{if(RP.on)return;}catch(e){}
const cs=window.__D.candles;
const nk={t:k.t,o:parseFloat(k.o),h:parseFloat(k.h),l:parseFloat(k.l),c:parseFloat(k.c),v:parseFloat(k.v)};
if(cs.length&&cs[cs.length-1].t===nk.t){cs[cs.length-1]=nk;}else{cs.push(nk);if(cs.length>120)cs.shift();}
window.__D.price=nk.c;
const pe=document.getElementById('p');if(pe)pe.textContent=nk.c;
requestDraw();}catch(e){}};
ws.onerror=function(){};}catch(e){}}
startWS('5m');async function loadStrip(){const tfs=['15m','1h','4h','1d'];let h='';
for(const tf of tfs){try{const r=await (await fetch('/api/history?tf='+tf,{cache:'no-store'})).json();
if(!r.ok||!r.candles.length)continue;
const cs=r.candles.slice(-120),id='sp_'+tf;
h+='<div style="flex:1;cursor:pointer" data-jump="'+tf+'"><div style="font-size:11px;color:#8a8a8a">'+tf.toUpperCase()+' '+cs[cs.length-1].c+'</div><canvas id="'+id+'" style="width:100%;height:64px;display:block"></canvas></div>';
setTimeout(()=>{const cv=document.getElementById(id);if(!cv)return;
const DPR=window.devicePixelRatio||1,W=cv.clientWidth||200,H=64;
cv.width=W*DPR;cv.height=H*DPR;const ctx=cv.getContext('2d');ctx.setTransform(DPR,0,0,DPR,0,0);
let hi=-1e18,lo=1e18;cs.forEach(c=>{hi=Math.max(hi,c.h);lo=Math.min(lo,c.l);});
const pad=(hi-lo)*0.1||1;hi+=pad;lo-=pad;
const X=i=>2+i*(W-4)/cs.length,Y=p=>H-4-(p-lo)/(hi-lo)*(H-8);
const up=cs[cs.length-1].c>=cs[0].c;ctx.strokeStyle=up?'#22c55e':'#ef4444';ctx.lineWidth=1.5;ctx.beginPath();
cs.forEach((c,i)=>{const x=X(i),y=Y(c.c);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.stroke();
ctx.fillStyle=up?'#22c55e':'#ef4444';ctx.beginPath();ctx.arc(X(cs.length-1),Y(cs[cs.length-1].c),2.5,0,7);ctx.fill();
},0);}catch(e){}}
document.getElementById('strip').innerHTML=h;document.querySelectorAll('#strip [data-jump]').forEach(function(el){el.onclick=function(){setTF(el.dataset.jump);};});}
loadStrip();setInterval(loadStrip,120000);document.addEventListener('keydown',e=>{const t=(e.target&&e.target.tagName)||'';if(t==='INPUT'||t==='SELECT'||t==='TEXTAREA')return;const V=window.__V=window.__V||{off:0,zoom:1};if(e.key==='+'||e.key==='='){V.zoom=Math.min(8,V.zoom*1.2);if(window.__D)drawChart(window.__D);}else if(e.key==='-'){V.zoom=Math.max(1,V.zoom/1.2);if(window.__D)drawChart(window.__D);}else if(e.key==='0'){window.__V={off:0,zoom:1};if(window.__D)drawChart(window.__D);}else if(e.key==='f'||e.key==='F'){document.getElementById('df').click();}else if(e.key==='l'||e.key==='L'){document.getElementById('dth').click();}});setInterval(tick,3000);setInterval(t,15000);t();
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
document.getElementById('rlive').onclick=()=>{if(RP.on){clearInterval(RP.timer);RP.on=false;}document.getElementById('rplay').textContent='Play';document.getElementById('rinfo').textContent='live wapas';window.__V={off:0,zoom:1};window.__LIVE=true;syncLiveBtn();t();};
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
        elif self.path.startswith("/api/tick"):
            try:
                import requests as _rq2
                q = _rq2.get("https://fapi.binance.com/fapi/v1/ticker/price",
                             params={"symbol": SYMBOL}, timeout=5).json()
                self._json({"ok": True, "price": float(q["price"]), "t": int(time.time() * 1000)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)[:100]}, 500)
        elif self.path.startswith("/api/history"):
            from urllib.parse import urlparse, parse_qs  # replay: file se pichli candles
            tf = parse_qs(urlparse(self.path).query).get("tf", ["5m"])[0]
            if tf not in ALL_TF:
                self._json({"ok": False, "error": "galat timeframe"}, 400)
                return
            try:
                q = parse_qs(urlparse(self.path).query)
                before = int(q.get("before", [0])[0] or 0)
                rows = json.loads((Path(__file__).resolve().parents[2] / "data" / f"BTCUSDT_{tf}.json").read_text())
                if before:
                    rows = [r for r in rows if r[0] < before][-500:]
                else:
                    rows = rows[-500:]
                self._json({"ok": True, "tf": tf, "count": len(rows),
                            "candles": [{"t": r[0], "o": float(r[1]), "h": float(r[2]),
                                         "l": float(r[3]), "c": float(r[4]), "v": float(r[5])} for r in rows]})
            except Exception as e:
                self._json({"ok": False, "error": str(e)[:150]}, 500)
        elif self.path.startswith("/api/footprint"):
            # footprint: ek band candle ke andar ke ASLI aggTrades, price-step par bucket.
            # m=true → buyer maker → SELL (bid par); m=false → BUY (ask par). Koi fake number nahi.
            from urllib.parse import urlparse, parse_qs  # footprint: candle-window trades
            q = parse_qs(urlparse(self.path).query)
            tf = q.get("tf", ["5m"])[0]
            if tf not in ALL_TF:
                self._json({"ok": False, "error": "galat timeframe"}, 400)
                return
            try:
                t0 = int(q.get("t", [0])[0] or 0)
                step = float(q.get("step", [0])[0] or 0)
            except Exception:
                self._json({"ok": False, "error": "t/step galat"}, 400)
                return
            if not t0:
                self._json({"ok": False, "error": "candle t chahiye"}, 400)
                return
            t1 = t0 + TF_MS[tf] - 1
            try:
                import requests as _rq3
                trades: list = []
                params: dict = {"symbol": SYMBOL, "startTime": t0, "endTime": t1, "limit": 1000}
                for _ in range(3):  # ek candle me max ~3000 trades (latency cap)
                    batch = _rq3.get("https://fapi.binance.com/fapi/v1/aggTrades",
                                     params=params, timeout=10).json()
                    if not isinstance(batch, list) or not batch:
                        break
                    trades += batch
                    if len(batch) < 1000:
                        break
                    if batch[0].get("T", 0) > t1:
                        break
                    params = {"symbol": SYMBOL, "fromId": batch[-1]["a"] + 1, "limit": 1000}
                rows = [x for x in trades if t0 <= x.get("T", 0) <= t1]
                if not rows:
                    self._json({"ok": False, "error": "is candle ka trade data nahi",
                                "unavailable": True}, 200)
                    return
                px = [float(x["p"]) for x in rows]
                if step <= 0:
                    step = max(0.1, round((max(px) - min(px)) / 12, 1))
                bk: dict = {}
                for x in rows:
                    p = float(x["p"])
                    qv = float(x["q"])
                    b = round((p // step) * step, 1)
                    r = bk.setdefault(b, [0.0, 0.0])
                    if x.get("m"):
                        r[0] += qv  # bid (sell-initiated)
                    else:
                        r[1] += qv  # ask (buy-initiated)
                out = [{"p": b, "bid": round(v[0], 3), "ask": round(v[1], 3),
                        "tot": round(v[0] + v[1], 3),
                        "delta": round(v[1] - v[0], 3)} for b, v in sorted(bk.items())]
                self._json({"ok": True, "tf": tf, "t": t0, "step": step,
                            "n": len(rows), "capped": len(trades) >= 3000, "rows": out})
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
    def _fill_hist():  # restart par file-history ko ab tak bharo (seam/gap na rahe)
        try:
            from market.history import download
            for tf in ALL_TF:
                try:
                    download(tf)
                except Exception as e:
                    _note(f"history {tf}: {str(e)[:60]}")
        except Exception as e:
            _note(f"history fill: {str(e)[:60]}")
    threading.Thread(target=_fill_hist, daemon=True).start()
    print(f"Dashboard: http://127.0.0.1:{PORT}", flush=True)
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except OSError:
        print(f"PORT {PORT} busy hai - purana server band karo ya PORT badlo", flush=True)
        raise SystemExit(1)
