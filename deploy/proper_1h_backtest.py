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

tf_1h = load('1h', 5000)
tf_4h = load('4h', 2000)

from engine.signal import htf_bias, generate_signal
from paper.journal import Engine

# Run proper 1h backtest (gated by 4h bias)
print('Running proper 1h backtest...')
e = Engine()
trades = 0
for i in range(40, len(tf_1h)):
    # Get 4h bias
    j = 0
    tf_4h = load('4h', 2000)
    while j + 1 < len(tf_4h) and tf_4h[j + 1].time <= tf_1h[i].time:
        j += 1
    if j >= len(tf_4h) or tf_4h[j].time > tf_1h[i].time:
        continue
    bias = htf_bias(tf_4h[:j+1], j)
    if bias == 'WAIT':
        continue
    sig = generate_signal(tf_1h[:i+1], i, bias=bias, check_kill_zone=False)
    if sig:
        # Check bias alignment
        if (bias == 'UP' and sig.side != 'long') or (bias == 'DOWN' and sig.side != 'short'):
            continue
        e.queue(sig, '1h')
    e.on_candle('1h', tf_1h[i], 3600000)

s = e.summary()
print('1h: {} trades, {} wins, {:.1f}% win, avg R: {:.3f}, equity: ${:.2f}'.format(s['closed'], s['wins'], s['win_rate'], s['avg_r'], s['equity']))
for t in e.closed:
    print('  {} {} entry={:.1f} stop={:.1f} target={:.1f} exit={:.1f} reason={} R={:.2f}'.format(
        t.id, t.side, t.entry, t.stop, t.target, t.exit, t.exit_reason, t.r_multiple))