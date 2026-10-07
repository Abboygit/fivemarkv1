#!/usr/bin/env python3
"""
Comprehensive Win-Maximizing Backtest
Tests all combinations of: RR targets, stop multipliers, filters
Finds the best configuration on 1-year data
"""
import sys
import json
import time
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


def run_backtest(config, tf_5m, tf_1h, label):
    """Run backtest with given config"""
    from engine.signal import htf_bias, pullback_pct, generate_signal
    from paper.journal import Engine
    from engine.primitives import atr

    # Override config in signal module
    import engine.signal as sig_mod
    old_disp_atr = sig_mod.DISP_ATR
    old_disp_range = sig_mod.DISP_RANGE_ATR
    old_rr = sig_mod.RISK_REWARD
    old_min_atr = sig_mod.MIN_STOP_ATR_MULT
    old_lookback = sig_mod.LOOKBACK

    sig_mod.DISP_ATR = config.get('disp_atr', 1.0)
    sig_mod.DISP_RANGE_ATR = config.get('disp_range', 1.3)
    sig_mod.RISK_REWARD = config.get('rr', 2.5)
    sig_mod.MIN_STOP_ATR_MULT = config.get('min_stop_atr', 1.5)
    sig_mod.LOOKBACK = config.get('lookback', 18)

    ltf = tf_5m
    htf = tf_1h
    e = Engine()
    j = 0
    n_sig = 0

    for i in range(40, len(tf_5m)):
        while j + 1 < len(tf_1h) and tf_1h[j + 1].time <= tf_5m[i].time:
            j += 1
        if tf_1h[j].time > tf_5m[i].time:
            continue
        htf = tf_1h[:j + 1]
        bias = htf_bias(htf, j)
        sig = generate_signal(tf_5m[:i + 1], i, bias=bias)
        if sig:
            e.queue(sig, '5m')
        e.on_candle('5m', tf_5m[i], 5 * 60 * 1000)

    s = e.summary()
    rs = [t.r_multiple for t in e.closed]
    avg_r = sum(rs) / len(rs) if rs else 0

    sig_mod.DISP_ATR = old_disp_atr
    sig_mod.DISP_RANGE_ATR = old_disp_range
    sig_mod.RISK_REWARD = old_rr
    sig_mod.MIN_STOP_ATR_MULT = old_min_atr
    sig_mod.LOOKBACK = old_lookback

    return {
        'label': label,
        'trades': s['closed'],
        'wins': s['wins'],
        'win_rate': s['win_rate'],
        'avg_r': round(avg_r, 3),
        'equity': round(s['equity'], 2),
        'net_r': round(sum(rs), 2),
        'config': config
    }


if __name__ == "__main__":
    print("Loading data...")
    tf_5m = load_candles('5m', 100000)[:-1]
    tf_1h = load_candles('1h', 9000)[:-1]
    print(f"Data: 5m={len(tf_5m)}, 1h={len(tf_1h)}")

    # All configurations to test
    configs = [
        # Baseline
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 2.5, 'min_stop_atr': 1.5, 'label': 'baseline'},

        # RR variations
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 3.0, 'min_stop_atr': 1.5, 'label': 'rr_3.0'},
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 3.5, 'min_stop_atr': 1.5, 'label': 'rr_3.5'},
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 4.0, 'min_stop_atr': 1.5, 'label': 'rr_4.0'},

        # Stop variations
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 2.5, 'min_stop_atr': 2.0, 'label': 'stop_2.0atr'},
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 2.5, 'min_stop_atr': 2.5, 'label': 'stop_2.5atr'},
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 3.0, 'min_stop_atr': 2.0, 'label': 'rr3_stop2.0atr'},
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 3.0, 'min_stop_atr': 2.5, 'label': 'rr3_stop2.5atr'},

        # Displacement variations
        {'disp_atr': 1.2, 'disp_range': 1.5, 'rr': 2.5, 'min_stop_atr': 1.5, 'label': 'disp_tight'},
        {'disp_atr': 1.2, 'disp_range': 1.5, 'rr': 3.0, 'min_stop_atr': 2.0, 'label': 'disp_tight_rr3_stop2.0'},
        {'disp_atr': 0.8, 'disp_range': 1.1, 'rr': 2.5, 'min_stop_atr': 1.5, 'label': 'disp_loose'},

        # Lookback variations
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 2.5, 'min_stop_atr': 1.5, 'lookback': 12, 'label': 'lb_12'},
        {'disp_atr': 1.0, 'disp_range': 1.3, 'rr': 2.5, 'min_stop_atr': 1.5, 'lookback': 24, 'label': 'lb_24'},
    ]

    print(f"Testing {len(configs)} configurations on 1-year data...")
    print("=" * 80)

    results = []
    for cfg in configs:
        label = cfg.pop('label')
        print(f"\nTesting: {label}...")
        start = time.time()
        result = run_backtest(cfg, tf_5m, tf_1h, label)
        result['label'] = label
        elapsed = time.time() - start
        print(f"  Trades: {result['trades']}, Win%: {result['win_rate']:.1f}, Avg R: {result['avg_r']:.3f}, Equity: ${result['equity']:.2f} ({elapsed:.1f}s)")
        results.append(result)

    # Restore defaults
    import engine.signal as sig_mod
    sig_mod.DISP_ATR = 1.0
    sig_mod.DISP_RANGE_ATR = 1.3
    sig_mod.RISK_REWARD = 2.5
    sig_mod.MIN_STOP_ATR_MULT = 1.5
    sig_mod.LOOKBACK = 18

    # Sort by avg_r (best first)
    results.sort(key=lambda x: x['avg_r'], reverse=True)

    print("\n" + "=" * 80)
    print("FINAL RESULTS (sorted by Avg R)")
    print("=" * 80)
    print(f"{'Config':<30} {'Trades':>6} {'Win%':>6} {'Avg R':>8} {'Equity':>10} {'Net R':>8}")
    print("-" * 80)
    for r in results:
        print(f"{r['label']:<30} {r['trades']:>6} {r['win_rate']:>5.1f}% {r['avg_r']:>8.3f} ${r['equity']:>9.2f} {r['net_r']:>8.2f}")

    # Save best config
    best = results[0]
    print(f"\n🏆 BEST: {best['label']}")
    print(f"   Avg R: {best['avg_r']:.3f}, Win%: {best['win_rate']:.1f}%, Trades: {best['trades']}")
    print(f"   Config: {best['config']}")