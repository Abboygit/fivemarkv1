"""Backtest v2 — NO look-ahead (user priority #1 fix).

Purani galtiyan (backtest_full.py):
  1. bias = htf_bias(htf, len(htf)-1) ek baar poore loop ke liye  -> future leak
  2. pullback_pct(htf[:len(htf)], i) me 5m index 1h array par     -> galat alignment

Ab: har 5m candle i par SIRF us waqt band ho chuki 1h candles se bias/pullback.
Mapping: sab se bada j jahan htf[j].time <= ltf[i].time (incremental pointer).
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')

from market.binance import Candle
from engine.signal import generate_signal, htf_bias, pullback_pct
from paper.journal import Engine

DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')
N_5M = 100000  # ~1 lakh candles ~ 1 year


def load(tf, limit):
    rows = json.loads((DATA_DIR / ('BTCUSDT_%s.json' % tf)).read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]),
                          low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


ltf = load('5m', N_5M)[:-1]   # aakhri chalti candle bahar (live jaisa)
htf_all = load('1h', N_5M // 12 + 60)[:-1]
print('5m:', len(ltf), '1h:', len(htf_all))

e = Engine()
j = 0
n_sig = n_ct = 0
worst_violation = 0
ALLOW_CT = '--no-ct' not in sys.argv
for i in range(40, len(ltf)):
    # incremental pointer: aakhri band 1h candle jahan htf[j].time <= ltf[i].time
    while j + 1 < len(htf_all) and htf_all[j + 1].time <= ltf[i].time:
        j += 1
    if htf_all[j].time > ltf[i].time:
        worst_violation += 1
        continue
    htf = htf_all[:j + 1]
    bias = htf_bias(htf, j)
    pb = pullback_pct(htf, j)
    sig = generate_signal(ltf[:i + 1], i, bias=bias)
    if sig:
        n_sig += 1
        e.queue(sig, '5m')
    e.on_candle('5m', ltf[i], 5 * 60 * 1000)

s = e.summary()
print('signals:', n_sig)
print('trades:', s['closed'], 'wins:', s['wins'], 'win_rate:', s['win_rate'],
      'equity:', s['equity'], 'avg_r:', s.get('avg_r'))
print('time-guard violations:', worst_violation)
print('invalid geometry skipped:', s.get('invalid_skipped'))
print('--- closed trades ---')
for t in e.closed:
    print('%s %s entry=%.1f stop=%.1f target=%.1f exit=%.1f %s R=%.2f' % (
        t.id, t.side, t.entry, t.stop, t.target, t.exit, t.exit_reason,
        t.r_multiple))
