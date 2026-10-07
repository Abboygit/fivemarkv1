import sys
import json
from pathlib import Path
sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\src')

from market.binance import Candle
from engine.signal import generate_signal, htf_bias, pullback_pct
from paper.journal import Engine

# Load cached data
DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')

def load_candles(tf, limit):
    f = DATA_DIR / f'BTCUSDT_{tf}.json'
    data = json.loads(f.read_text())
    candles = []
    for row in data[-limit:]:
        c = Candle(
            time=row[0],
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5])
        )
        candles.append(c)
    return candles

ltf = load_candles('5m', 5000)[:-1]
htf = load_candles('1h', 5000)[:-1]
bias = htf_bias(htf, len(htf)-1)
print('bias:', bias, 'ltf len:', len(ltf))

e = Engine()
trades_count = 0
counter_count = 0
for i in range(40, len(ltf)):
    pb = pullback_pct(htf[:len(htf)], i)
    sig = generate_signal(ltf[:i+1], i, bias=bias, allow_counter=True, pullback=pb)
    if sig:
        if sig.counter_trend:
            counter_count += 1
        print(f'i={i} side={sig.side} entry={sig.entry:.1f} stop={sig.stop:.1f} target={sig.target:.1f} rr={sig.rr:.2f} zone={sig.zone_kind} counter={sig.counter_trend}')
        e.queue(sig, '5m')
        trades_count += 1
    e.on_candle('5m', ltf[i], 5*60*1000)

s = e.summary()
print('trades:', s['closed'], 'wins:', s['wins'], 'win_rate:', s['win_rate'], 'equity:', s['equity'])
print('signals generated:', trades_count, 'counter:', counter_count)