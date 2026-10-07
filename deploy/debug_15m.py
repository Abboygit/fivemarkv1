import sys
sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')
import json
from pathlib import Path
from market.binance import Candle
from engine.signal import _displacement, _sweep, _mss_or_bos, _fvg_zone, _ob_zone, _overlaps, confirmed_swings, generate_signal, htf_bias

DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')

def load(tf, limit):
    rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'BTCUSDT_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out

tf_15m = load('15m', 2000)

from engine.signal import _displacement, _sweep, _mss_or_bos, _fvg_zone, _ob_zone, _overlaps, confirmed_swings, generate_signal, htf_bias

# Test at i=100
i = 100
candles = tf_15m[:i+1]
cur = tf_15m[i]
print(f'cur: O={cur.open:.1f} H={cur.high:.1f} L={cur.low:.1f} C={cur.close:.1f}')

# Check displacements in lookback
for ev in range(i, max(i-18, 0)-1, -1):
    direction = _displacement(tf_15m, ev)
    if not direction:
        continue
    sweep = None
    from engine.signal import _sweep, _mss_or_bos, _fvg_zone, _ob_zone, _overlaps
    sweep = _sweep(tf_15m[:i+1], ev)
    struct = _mss_or_bos(tf_15m[:i+1], ev, direction)
    if not sweep and not struct:
        print(f'ev={ev} direction={direction} sweep={sweep} struct={struct} -> SKIP')
        continue
    print(f'ev={ev} direction={direction} sweep={sweep} struct={struct} -> CHECKING ZONE')
    zone = _fvg_zone(tf_15m[:ev+1], ev, direction) or _ob_zone(tf_15m[:ev+1], ev, direction)
    if not zone or zone['index'] >= i:
        print(f'  zone invalid: {zone}')
        continue
    cur = tf_15m[i]
    if cur.low <= zone['high'] and cur.high >= zone['low']:
        print(f'  OVERLAP! zone={zone}')
    else:
        print(f'  NO OVERLAP: cur.low={tf_15m[i].low:.1f} cur.high={tf_15m[i].high:.1f} zone={zone}')