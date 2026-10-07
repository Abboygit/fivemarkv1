import sys
sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')
import json
from pathlib import Path
from market.binance import Candle
from engine.signal import htf_bias, _displacement, _sweep, _mss_or_bos, _fvg_zone, _ob_zone, _overlaps, generate_signal, htf_bias

DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')

def load(tf, limit):
    rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'BTCUSDT_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out

tf_5m = load('5m', 2000)
tf_1h = load('1h', 2000)

from engine.signal import htf_bias, _displacement, _sweep, _mss_or_bos, _fvg_zone, _ob_zone, _overlaps

# Test at i=100 where bias is DOWN
i = 100
j = 0
tf_1h_data = load('1h', 2000)
tf_5m_data = load('5m', 2000)

while j + 1 < len(tf_1h) and tf_1h[j + 1].time <= tf_5m[i].time:
    j += 1
bias = htf_bias(tf_1h[:j+1], j)
print(f'bias at i={i}: {bias}')

# Trace signal generation step by step
candles = tf_5m[:i+1]
index = i
cur = tf_5m[i]

from engine.signal import _displacement, _sweep, _mss_or_bos, _fvg_zone, _ob_zone, _overlaps

# Check displacements in lookback
for ev in range(i, max(i-18, 0)-1, -1):
    d = _displacement(tf_5m, ev)
    if not d:
        continue
    sweep = _sweep(ltf[:i+1], ev)
    struct = _mss_or_bos(ltf[:i+1], ev, d)
    if not sweep and not struct:
        print(f'ev={ev} direction={d} sweep={sweep} struct={struct} -> SKIP')
        continue
    print(f'ev={ev} direction={d} sweep={sweep} struct={struct} -> CHECKING ZONE')
    zone = None
    if d == 'bullish':
        zone = _fvg_zone(ltf[:ev+1], ev, 'bullish') or _ob_zone(ltf[:ev+1], ev, 'bullish')
    else:
        zone = _fvg_zone(ltf[:ev+1], ev, 'bearish') or _ob_zone(ltf[:ev+1], ev, 'bearish')
    if not zone or zone['index'] >= i:
        print(f'  zone invalid: {zone}')
        continue
    if ltf[i].low <= zone['high'] and ltf[i].high >= zone['low']:
        print(f'  OVERLAP! zone={zone}')
    else:
        print(f'  NO OVERLAP: cur.low={ltf[i].low:.1f} cur.high={ltf[i].high:.1f} zone={zone}')

