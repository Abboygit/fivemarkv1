#!/usr/bin/env python3
"""
Test individual filters: Volume, Session, ADX
Then test combined
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')

from market.binance import Candle
from engine.signal import htf_bias, pullback_pct, generate_signal
from paper.journal import Engine
from engine.primitives import atr

DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')


def load_candles(tf, limit):
    rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'BTCUSDT_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


def adx(candles, index, period=14):
    """Calculate ADX at given index"""
    if index < period + 1:
        return 0.0
    
    tr_sum = 0.0
    plus_dm_sum = 0.0
    minus_dm_sum = 0.0
    
    for i in range(index - period + 1, index + 1):
        if i == 0:
            continue
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_sum += tr
        
        up_move = high - candles[i - 1].high
        down_move = candles[i - 1].low - low
        
        if up_move > down_move and up_move > 0:
            plus_dm_sum += up_move
        elif down_move > up_move and down_move > 0:
            minus_dm_sum += down_move
    
    if tr_sum == 0:
        return 0.0
    
    plus_di = 100 * (plus_dm_sum / tr_sum)
    minus_di = 100 * (minus_dm_sum / tr_sum)
    
    if plus_di + minus_di == 0:
        return 0.0
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    
    # Smooth DX for ADX (simplified - just return DX for now)
    return dx


def run_backtest(config, label, tf_5m, tf_1h):
    """Run backtest with given filters"""
    import engine.signal as sig_mod
    
    # Save defaults
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
    
    # Store filter settings
    sig_mod.VOLUME_FILTER = config.get('volume_filter', False)
    sig_mod.VOLUME_MULT = config.get('volume_mult', 1.5)
    sig_mod.SESSION_FILTER = config.get('session_filter', False)
    sig_mod.ADX_FILTER = config.get('adx_filter', False)
    sig_mod.ADX_THRESHOLD = config.get('adx_threshold', 20)
    
    ltf = load_candles('5m', 100000)[:-1]
    htf = load_candles('1h', 9000)[:-1]
    
    from engine.signal import htf_bias, pullback_pct, generate_signal
    from paper.journal import Engine
    
    e = Engine()
    j = 0
    n_sig = 0
    
    for i in range(40, len(ltf)):
        while j + 1 < len(tf_1h) and tf_1h[j + 1].time <= tf_5m[i].time:
            j += 1
        if tf_1h[j].time > tf_5m[i].time:
            continue
        htf = tf_1h[:j + 1]
        bias = htf_bias(htf, j)
        
        # Volume filter check
        if sig_mod.VOLUME_FILTER:
            if i == 0:
                continue
            vol_avg = sum(c.volume for c in tf_5m[max(0, i-20):i]) / min(20, i)
            if tf_5m[i].volume < vol_avg * sig_mod.VOLUME_MULT:
                e.on_candle('5m', tf_5m[i], 5 * 60 * 1000)
                continue
        
        # Session filter (London/NY: 13-17 UTC, 08-12 EST)
        if sig_mod.SESSION_FILTER:
            from datetime import datetime
            dt = datetime.fromtimestamp(tf_5m[i].time / 1000)
            hour = dt.hour
            if not (8 <= hour <= 16):  # London 8-16 UTC overlaps NY 8-12 EST
                e.on_candle('5m', tf_5m[i], 5 * 60 * 1000)
                continue
        
        # ADX filter
        if sig_mod.ADX_FILTER:
            if i < 20:
                e.on_candle('5m', tf_5m[i], 5 * 60 * 1000)
                continue
            adx_val = adx(ltf, i)
            if adx_val < sig_mod.ADX_THRESHOLD:
                e.on_candle('5m', tf_5m[i], 5 * 60 * 1000)
                continue
        
        # Regular signal generation
        while j + 1 < len(tf_1h) and tf_1h[j + 1].time <= tf_5m[i].time:
            j += 1
        if tf_1h[j].time > tf_5m[i].time:
            continue
        htf = tf_1h[:j + 1]
        bias = htf_bias(htf, j)
        sig = generate_signal(ltf[:i + 1], i, bias=bias)
        if sig:
            e.queue(sig, '5m')
        e.on_candle('5m', tf_5m[i], 5 * 60 * 1000)
    
    s = e.summary()
    rs = [t.r_multiple for t in e.closed]
    avg_r = sum(rs) / len(rs) if rs else 0
    
    return {
        'trades': s['closed'],
        'wins': s['wins'],
        'win_rate': s['win_rate'],
        'avg_r': round(avg_r, 3),
        'equity': round(s['equity'], 2),
        'net_r': round(sum([t.r_multiple for t in e.closed]), 2)
    }


def load_candles(tf, limit):
    rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'BTCUSDT_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


if __name__ == "__main__":
    print("Loading data...")
    tf_5m = load_candles('5m', 100000)[:-1]
    tf_1h = load_candles('1h', 9000)[:-1]
    print(f"Data: 5m={len(tf_5m)}, 1h={len(tf_1h)}")
    
    tests = [
        {'volume_filter': False, 'session_filter': False, 'adx_filter': False, 'label': 'baseline'},
        {'volume_filter': True, 'volume_mult': 1.5, 'session_filter': False, 'adx_filter': False, 'label': 'volume_1.5x'},
        {'volume_filter': True, 'volume_mult': 2.0, 'session_filter': False, 'adx_filter': False, 'label': 'volume_2.0x'},
        {'volume_filter': False, 'session_filter': True, 'adx_filter': False, 'label': 'session_london_ny'},
        {'volume_filter': False, 'session_filter': False, 'adx_filter': True, 'adx_threshold': 20, 'label': 'adx_20'},
        {'volume_filter': False, 'session_filter': False, 'adx_filter': True, 'adx_threshold': 25, 'label': 'adx_25'},
        {'volume_filter': True, 'volume_mult': 1.5, 'session_filter': True, 'adx_filter': False, 'label': 'vol1.5_session'},
        {'volume_filter': True, 'volume_mult': 1.5, 'session_filter': False, 'adx_filter': True, 'adx_threshold': 20, 'label': 'vol1.5_adx20'},
        {'volume_filter': False, 'session_filter': True, 'adx_filter': True, 'adx_threshold': 20, 'label': 'session_adx20'},
        {'volume_filter': True, 'volume_mult': 1.5, 'session_filter': True, 'adx_filter': True, 'adx_threshold': 20, 'label': 'all_three'},
    ]
    
    print(f"Testing {len(tests)} filter combinations on 1-year data...")
    print("=" * 80)
    
    results = []
    for cfg in tests:
        label = cfg.pop('label')
        print(f"\nTesting: {label}...")
        start = time.time()
        result = run_backtest(cfg, label, tf_5m, tf_1h)
        result['label'] = label
        elapsed = time.time() - start
        print(f"  Trades: {result['trades']}, Win%: {result['win_rate']:.1f}, Avg R: {result['avg_r']:.3f}, Equity: ${result['equity']:.2f} ({elapsed:.1f}s)")
        results.append(result)
    
    # Sort by avg_r
    results.sort(key=lambda x: x['avg_r'], reverse=True)
    
    print("\n" + "=" * 80)
    print("FINAL RESULTS (sorted by Avg R)")
    print("=" * 80)
    print(f"{'Config':<25} {'Trades':>6} {'Win%':>6} {'Avg R':>8} {'Equity':>10} {'Net R':>8}")
    print("-" * 80)
    for r in results:
        print(f"{r['label']:<25} {r['trades']:>6} {r['win_rate']:>5.1f}% {r['avg_r']:>8.3f} ${r['equity']:>9.2f} {r['net_r']:>8.2f}")
    
    best = results[0]
    print(f"\nBEST: {best['label']}")
    print(f"   Avg R: {best['avg_r']:.3f}, Win%: {best['win_rate']:.1f}%, Trades: {best['trades']}")