#!/usr/bin/env python3
"""
4h → 1h → 5m Hierarchy Backtest with Paper Trading
4h bias gates 1h signals, 1h bias gates 5m signals
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')

from market.binance import Candle
from engine.signal import htf_bias, pullback_pct, generate_signal
from paper.journal import Engine

DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')


def load_candles(tf, limit):
    rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'BTCUSDT_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


def run_4h_1h_5m_backtest(limit_4h=2000):
    """Run 4h -> 1h -> 5m hierarchical backtest with paper trading"""
    
    tf_4h = load_candles('4h', limit_4h)[:-1]
    tf_1h = load_candles('1h', limit_4h * 4)[:-1]
    tf_5m = load_candles('5m', limit_4h * 48)[:-1]
    
    print(f"Loaded: 4h={len(tf_4h)}, 1h={len(tf_1h)}, 5m={len(tf_5m)}")
    
    e = Engine()
    idx_4h = idx_1h = 0
    n_sig_1h = n_sig_5m = 0
    
    for i_5m in range(40, len(tf_5m)):
        # Align 1h to 5m
        while idx_1h + 1 < len(tf_1h) and tf_1h[idx_1h + 1].time <= tf_5m[i_5m].time:
            idx_1h += 1
        if tf_1h[idx_1h].time > tf_5m[i_5m].time:
            continue
        
        # Align 4h to 1h (for 1h bias)
        while idx_4h + 1 < len(tf_4h) and tf_4h[idx_4h + 1].time <= tf_1h[idx_1h].time:
            idx_4h += 1
        if tf_4h[idx_4h].time > tf_1h[idx_1h].time:
            continue
        
        # 4h bias
        tf4h_now = tf_4h[:idx_4h + 1]
        bias_4h = htf_bias(tf4h_now, idx_4h)
        
        # 1h signal (gated by 4h bias)
        tf1h_now = tf_1h[:idx_1h + 1]
        sig_1h = generate_signal(tf1h_now[:idx_1h + 1], idx_1h, bias=bias_4h)
        
        if sig_1h:
            n_sig_1h += 1
            # Queue 1h trade (simulated)
        
        # 1h bias for 5m
        bias_1h = htf_bias(tf1h_now, idx_1h)
        
        # 5m signal (gated by 1h bias)
        tf5m_now = tf_5m[:i_5m + 1]
        sig_5m = generate_signal(tf5m_now, i_5m, bias=bias_1h)
        
        if sig_5m:
            n_sig_5m += 1
            e.queue(sig_5m, '5m')
        
        e.on_candle('5m', tf_5m[i_5m], 5 * 60 * 1000)
        
        if i_5m % 20000 == 0 and i_5m > 0:
            print(f"  Progress: 5m index {i_5m}, 1h sigs={n_sig_1h}, 5m sigs={n_sig_5m}, trades={len(e.closed)}")
    
    s = e.summary()
    print(f"\n4h->1h->5m Results:")
    print(f"  1h signals: {n_sig_1h}")
    print(f"  5m signals: {n_sig_5m}")
    print(f"  Trades: {s['closed']}, Wins: {s['wins']}, Win%: {s['win_rate']}%")
    print(f"  Equity: ${s['equity']:.2f}, Avg R: {s.get('avg_r', 0):.2f}")
    
    for t in e.closed:
        print(f"  {t.id} {t.side} entry={t.entry:.1f} stop={t.stop:.1f} target={t.target:.1f} exit={t.exit:.1f} {t.exit_reason} R={t.r_multiple:.2f}")


if __name__ == "__main__":
    run_4h_1h_5m_backtest(2000)