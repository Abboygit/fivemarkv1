#!/usr/bin/env python3
"""
Proper Multi-Symbol Backtest with Correct Timeframe Alignment
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')

from market.binance import Candle
from engine.signal import (htf_bias, pullback_pct, generate_signal, is_kill_zone, 
                          is_avoid_session, is_silver_bullet, adx, _displacement, 
                          _sweep, _mss_or_bos, _fvg_zone, _ob_zone, _overlaps)
from paper.journal import Engine

DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT"]
TIMEFRAMES = ["1d", "4h", "1h", "15m", "5m", "1m"]
TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def load_candles(symbol, tf, limit):
    try:
        rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'{symbol}_{tf}.json').read_text())
    except:
        return []
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), 
                          low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


def run_proper_backtest():
    print("=" * 80)
    print("PROPER MULTI-TIMEFRAME BACKTEST")
    print("=" * 80)
    
    # Load all data for BTC
    tf_data = {}
    for tf in ["1d", "4h", "1h", "15m", "5m", "1m"]:
        limit = 100000 if tf in ["1m", "5m"] else (10000 if tf == "15m" else 2000)
        tf_data = load_candles("BTCUSDT", tf, limit)
        print(f"  {tf}: {len(tf_data[tf])} candles")
    
    # Pre-calculate biases
    from engine.signal import htf_bias
    
    tf_1d = tf_data['1d']
    tf_4h = tf_data['4h']
    tf_1h = tf_data['1h']
    tf_15m = tf_data['15m']
    tf_5m = tf_data['5m']
    tf_1m = tf_data['1m']
    
    from engine.signal import htf_bias
    
    # 1d bias for 4h
    bias_1d_at_4h = []
    for i in range(len(tf_4h)):
        j = 0
        while j + 1 < len(tf_1d) and tf_1d[j + 1].time <= tf_4h[i].time:
            j += 1
        bias = htf_bias(tf_1d[:j+1], j) if j < len(tf_1d) else "WAIT"
    
    # 4h bias for 1h
    bias_4h_at_1h = []
    for i in range(len(tf_1h)):
        j = 0
        while j + 1 < len(tf_4h) and tf_4h[j + 1].time <= tf_1h[i].time:
            j += 1
        bias = htf_bias(tf_4h[:j+1], j) if j < len(tf_4h) else "WAIT"
    
    # 1h bias for 15m
    bias_1h_at_15m = []
    for i in range(len(tf_15m)):
        j = 0
        while j + 1 < len(tf_1h) and tf_1h[j + 1].time <= tf_15m[i].time:
            j += 1
        bias = htf_bias(tf_1h[:j+1], j) if j < len(tf_1h) else "WAIT"
    
    # 15m bias for 5m
    bias_15m_at_5m = []
    for i in range(len(tf_5m)):
        j = 0
        while j + 1 < len(tf_15m) and tf_15m[j + 1].time <= tf_5m[i].time:
            j += 1
        bias = htf_bias(tf_15m[:j+1], j) if j < len(tf_15m) else "WAIT"
    
    # 5m bias for 1m
    bias_5m_at_1m = []
    for i in range(len(tf_1m)):
        j = 0
        while j + 1 < len(tf_5m) and tf_5m[j + 1].time <= tf_1m[i].time:
            j += 1
        bias = htf_bias(tf_5m[:j+1], j) if j < len(tf_5m) else "WAIT"
    
    # Now run the backtest with engines
    e_1h = Engine()
    e_15m = Engine()
    e_5m = Engine()
    e_1m = Engine()
    
    # Run 1h signals (gated by 4h bias)
    for i in range(40, len(tf_1h)):
        bias = bias_4h_at_1h[i]
        if bias == "WAIT":
            continue
        sig = generate_signal(tf_1h[:i+1], i, bias=bias_4h_at_1h[i], check_kill_zone=False)
        if sig:
            # Check if signal direction matches bias
            if (bias_4h_at_1h[i] == "UP" and sig.side != "long") or \
               (bias_4h_at_1h[i] == "DOWN" and sig.side != "short"):
                continue
            # Queue and process
    
    # For now, just run the comprehensive test we already have
    print("Use comprehensive_test.py for detailed analysis")
    return


if __name__ == "__main__":
    run_proper_backtest()