import sys
sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')
import json
from pathlib import Path
from market.binance import Candle
from engine.signal import htf_bias, generate_signal
from paper.journal import Engine

DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')

def load(tf, limit):
    rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'BTCUSDT_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out

tf_1h = load('1h', 2000)
tf_15m = load('15m', 2000)

from engine.signal import htf_bias, generate_signal
from paper.journal import Engine

# Simulate the 15m backtest with engine
e = Engine()
found = 0
for i in range(40, 2000):
    j = 0
    while j + 1 < len(tf_1h) and tf_1h[j + 1].time <= tf_15m[i].time:
        j += 1
    if j >= len(tf_1h) or tf_1h[j].time > tf_15m[i].time:
        continue
    bias_1h = htf_bias(tf_1h[:j+1], j)
    if bias_1h == 'WAIT':
        continue
    sig = generate_signal(tf_15m[:i+1], i, bias=bias_1h, check_kill_zone=False)
    if sig:
        print(f'15m i={i} bias={bias_1h} signal={sig.side} entry={sig.entry:.1f} stop={sig.stop:.1f} target={sig.target:.1f} zone={sig.zone_kind}')
        e.queue(sig, '15m')
        found += 1
    e.on_candle('15m', tf_15m[i], 900000)
    if found > 10:
        break

if not found:
    print('No 15m signals found')

s = e.summary()
print('Trades:', s['closed'], 'Wins:', s['wins'], 'Win%:', s['win_rate'], 'Avg R:', s['avg_r'])
for t in e.closed:
    print(f'  {t.id} {t.side} entry={t.entry:.1f} stop={t.stop:.1f} target={t.target:.1f} exit={t.exit:.1f} reason={t.exit_reason} R={t.r_multiple:.2f}')