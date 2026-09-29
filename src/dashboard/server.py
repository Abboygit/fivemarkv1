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
TF_MS = {"5m": 5 * 60 * 1000, "1h": 60 * 60 * 1000}
REFRESH_SEC = 20

STATE: dict = {"updated_at": 0, "ok": False, "error": "", "symbol": SYMBOL,
               "price": 0.0, "bias": "WAIT", "signal": None, "paper": {},
               "timeframes": {}, "log": []}
ENGINE = Engine()
LAST_CLOSED: dict = {}


def _note(msg: str) -> None:
    STATE["log"] = ([f"{time.strftime('%H:%M:%S')} {msg}"] + STATE["log"])[:10]


def refresh_once() -> None:
    try:
        ltf = fetch_klines(SYMBOL, LTF, 120)[:-1]  # band only
        htf = fetch_klines(SYMBOL, HTF, 120)[:-1]
        for tf, candles in ((LTF, ltf), (HTF, htf)):
            v = validate_candles(candles, TF_MS[tf])
            STATE["timeframes"][tf] = {"ok": v.valid, "score": v.score, "close": candles[-1].close}
            if not v.valid:
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
.note{margin-top:8px;color:#6a6a72;font-size:12px}</style></head><body>
<div class="bar"><span class="logo">FIVE MARK V1</span><span class="sym">BTCUSDT</span>
<span class="pr" id="p">…</span><span class="st" id="s">…</span></div>
<div class="eng" id="e">ENGINE: load ho raha hai…</div>
<div class="grid">
<div class="card"><h3>HTF RUKH (1h)</h3><div class="big" id="b">…</div></div>
<div class="card"><h3>SIGNAL (5m)</h3><div class="big" id="g">…</div></div>
<div class="card"><h3>PAPER ($10k)</h3><div class="big" id="w">…</div></div>
</div>
<div class="grid"><div class="card"><h3>LOG (taza pehle)</h3><div class="log" id="l">…</div></div></div>
<p class="note">Live dashboard — 3-sec refresh. Design: Dashboard design.md (LOCKED).</p>
<script>
async function t(){try{const r=await fetch('/api/state',{cache:'no-store'});const d=await r.json();
document.getElementById('p').textContent=d.price||'…';
document.getElementById('s').innerHTML=d.ok?'<span class=ok>● DATA OK</span>':'<span class=bad>● '+d.error+'</span>';
document.getElementById('b').textContent=d.bias||'…';
document.getElementById('g').textContent=d.signal?(d.signal.side+' '+d.signal.event+' RR '+d.signal.rr):'koi entry nahi';
document.getElementById('w').textContent=d.paper.equity?('$'+d.paper.equity+' | '+d.paper.closed+' trades'):'…';
document.getElementById('e').textContent='ENGINE: rukh '+d.bias+' | open '+((d.paper||{}).open||0)+' | '+(d.signal?('signal '+d.signal.side):'scan chal raha');
document.getElementById('l').innerHTML=(d.log||[]).join('<br>');}catch(e){}}
setInterval(t,3000);t();
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
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
