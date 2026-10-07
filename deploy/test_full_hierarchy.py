#!/usr/bin/env python3
"""
Test ALL timeframe hierarchies: 1d → 4h → 1h → 15m → 5m → 1m
Check win rates at each HTF→LTF level
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')

from market.binance import Candle
from engine.signal import htf_bias, pullback_pct, generate_signal, is_kill_zone, is_avoid_session, is_silver_bullet, adx
from paper.journal import Engine

DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')


def load_candles(tf, limit):
    rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'BTCUSDT_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


def run_hierarchy_test(tf_1d, tf_4h, tf_1h, tf_15m, tf_5m, tf_1m):
    """Run complete hierarchy: 1d -> 4h -> 1h -> 15m -> 5m -> 1m"""
    
    # Load all timeframes
    tf_1d_data = tf_1d
    tf_4h_data = tf_4h
    tf_1h_data = tf_1h
    tf_15m_data = tf_15m
    tf_5m_data = tf_5m
    tf_1m_data = tf_1m
    
    print(f"Loaded: 1d={len(tf_1d_data)}, 4h={len(tf_4h_data)}, 1h={len(tf_1h_data)}, 15m={len(tf_15m_data)}, 5m={len(tf_5m_data)}, 1m={len(tf_1m_data)}")
    
    # Indices for each timeframe
    idx_1d = idx_4h = idx_1h = idx_15m = idx_5m = idx_1m = 0
    
    e = Engine()
    stats = {
        '1d_bias': {'UP': 0, 'DOWN': 0, 'WAIT': 0},
        '4h_bias': {'UP': 0, 'DOWN': 0, 'WAIT': 0},
        '1h_bias': {'UP': 0, 'DOWN': 0, 'WAIT': 0},
        '15m_bias': {'UP': 0, 'DOWN': 0, 'WAIT': 0},
        'signals': {
            '1h': 0, '15m': 0, '5m': 0, '1m': 0
        },
        'trades': {
            '1h': 0, '15m': 0, '5m': 0, '1m': 0
        },
        'wins': {
            '1h': 0, '15m': 0, '5m': 0, '1m': 0
        },
        'htf_ltf_transitions': {
            '1d_to_4h': {'UP': 0, 'DOWN': 0},
            '4h_to_1h': {'UP': 0, 'DOWN': 0},
            '1h_to_15m': {'UP': 0, 'DOWN': 0},
            '15m_to_5m': {'UP': 0, 'DOWN': 0},
            '5m_to_1m': {'UP': 0, 'DOWN': 0},
        }
    }
    
    engines = {
        '1h': Engine(),
        '15m': Engine(),
        '5m': Engine(),
        '1m': Engine(),
    }
    
    idx_4h = idx_1h = idx_15m = idx_5m = idx_1m = 0
    
    print("Starting multi-timeframe backtest...")
    start_time = time.time()
    
    for i_1m in range(40, len(tf_1m_data)):
        # Progress
        if i_1m % 20000 == 0 and i_1m > 0:
            elapsed = time.time() - start_time
            print(f"  Progress: 1m index {i_1m}/{len(tf_1m_data)}, elapsed: {elapsed:.1f}s")
        
        # Align 1h to 1m
        while idx_1h + 1 < len(tf_1h_data) and tf_1h_data[idx_1h + 1].time <= tf_1m_data[i_1m].time:
            idx_1h += 1
        if tf_1h[idx_1h].time > tf_1m[i_1m].time:
            continue
        
        # Align 4h to 1h
        while idx_4h + 1 < len(tf_4h_data) and tf_4h[idx_4h + 1].time <= tf_1h[idx_1h].time:
            idx_4h += 1
        if tf_4h[idx_4h].time > tf_1h[idx_1h].time:
            continue
            
        # Align 1d to 4h
        while idx_1d + 1 < len(tf_1d_data) and tf_1d_data[idx_1d + 1].time <= tf_4h[idx_4h].time:
            idx_1d += 1
        if tf_1d[idx_1d].time > tf_4h[idx_4h].time:
            continue
        
        # Align 15m to 1h
        while idx_15m + 1 < len(tf_15m_data) and tf_15m_data[idx_15m + 1].time <= tf_1h[idx_1h].time:
            idx_15m += 1
        if tf_15m[idx_15m].time > tf_1h[idx_1h].time:
            continue
            
        # Align 5m to 15m
        while idx_5m + 1 < len(tf_5m_data) and tf_5m_data[idx_5m + 1].time <= tf_15m[idx_15m].time:
            idx_5m += 1
        if tf_5m[idx_5m].time > tf_15m[idx_15m].time:
            continue
        
        # Get biases at each level
        tf_1d_now = tf_1d[:idx_1d + 1]
        bias_1d = htf_bias(tf_1d[:idx_1d + 1], idx_1d)
        stats['1d_bias'][bias_1d] += 1
        
        tf_4h_now = tf_4h[:idx_4h + 1]
        bias_4h = htf_bias(tf_4h[:idx_4h + 1], idx_4h)
        stats['4h_bias'][bias_4h] += 1
        
        tf_1h_now = tf_1h[:idx_1h + 1]
        bias_1h = htf_bias(tf_1h[:idx_1h + 1], idx_1h)
        stats['1h_bias'][bias_1h] += 1
        
        tf_15m_now = tf_15m[:idx_15m + 1]
        bias_15m = htf_bias(tf_15m[:idx_15m + 1], idx_15m)
        stats['15m_bias'][bias_15m] += 1
        
        # Track HTF->LTF transitions
        if bias_1d != "WAIT":
            stats['htf_ltf_transitions']['1d_to_4h'][bias_1d] += 1
        if bias_4h != "WAIT":
            stats['htf_ltf_transitions']['4h_to_1h'][bias_4h] += 1
        if bias_1h != "WAIT":
            stats['htf_ltf_transitions']['1h_to_15m'][bias_1h] += 1
        if bias_15m != "WAIT":
            stats['htf_ltf_transitions']['15m_to_5m'][bias_15m] += 1
        
# Generate signals at each level
        # 1h signal (gated by 4h bias) - NO kill zone filter for HTF signals
        sig_1h = generate_signal(tf_1h[:idx_1h + 1], idx_1h, bias=bias_4h, check_kill_zone=False)
        if sig_1h:
            stats['signals']['1h'] += 1
            engines['1h'].queue(sig_1h, '1h')
        
        # 15m signal (gated by 1h bias) - NO kill zone filter for HTF signals
        sig_15m = generate_signal(tf_15m[:idx_15m + 1], idx_15m, bias=bias_1h, check_kill_zone=False)
        if sig_15m:
            stats['signals']['15m'] += 1
            engines['15m'].queue(sig_15m, '15m')
        
        # 5m signal (gated by 15m bias) - NO kill zone filter for HTF signals
        sig_5m = generate_signal(tf_5m[:idx_5m + 1], idx_5m, bias=bias_15m, check_kill_zone=False)
        if sig_5m:
            stats['signals']['5m'] += 1
            engines['5m'].queue(sig_5m, '5m')
        
        # 1m signal (ENTRY timeframe) - Apply kill zone and session filters
        if not is_kill_zone(tf_1m[i_1m]):
            e.on_candle('1m', tf_1m[i_1m], 60000)
            continue
        if is_avoid_session(tf_1m[i_1m]):
            e.on_candle('1m', tf_1m[i_1m], 60000)
            continue
        
        # 1m signal (gated by 5m bias) - ENTRY timeframe, apply filters
        tf_5m_now = tf_5m[:idx_5m + 1]
        bias_5m = htf_bias(tf_5m[:idx_5m + 1], idx_5m)
        sig_1m = generate_signal(tf_1m[:i_1m + 1], i_1m, bias=bias_5m, check_kill_zone=True)
        if sig_1m:
            stats['signals']['1m'] += 1
            engines['1m'].queue(sig_1m, '1m')
        
        # Update engines with current candles
        engines['1h'].on_candle('1h', tf_1h[idx_1h], 3600000)
        engines['15m'].on_candle('15m', tf_15m[idx_15m], 900000)
        engines['5m'].on_candle('5m', tf_5m[idx_5m], 300000)
        engines['1m'].on_candle('1m', tf_1m[i_1m], 60000)
        
        # Update trade stats
        for tf_name in ['1h', '15m', '5m', '1m']:
            eng = engines[tf_name]
            new_trades = len(eng.closed) - stats['trades'][tf_name]
            if new_trades > 0:
                stats['trades'][tf_name] = len(eng.closed)
                stats['wins'][tf_name] = sum(1 for t in eng.closed if t.r_multiple > 0)
        
        # Progress
        if i_1m % 20000 == 0 and i_1m > 0:
            elapsed = time.time() - start_time
            print(f"  Progress: 1m index {i_1m}/{len(tf_1m_data)}, elapsed: {time.time() - start_time:.1f}s")
    
    # Final stats
    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.1f}s")
    print("=" * 80)
    print("HIERARCHY TEST RESULTS")
    print("=" * 80)
    
    print("\n1. BIAS DISTRIBUTION:")
    for tf_name in ['1d', '4h', '1h', '15m']:
        bias_counts = stats[f'{tf_name}_bias']
        total = sum(bias_counts.values())
        if total > 0:
            print(f"  {tf_name}: UP={bias_counts['UP']} ({bias_counts['UP']/total*100:.1f}%), DOWN={bias_counts['DOWN']} ({bias_counts['DOWN']/total*100:.1f}%), WAIT={bias_counts['WAIT']} ({bias_counts['WAIT']/total*100:.1f}%)")
    
    print("\n2. SIGNALS GENERATED:")
    for tf_name in ['1h', '15m', '5m', '1m']:
        print(f"  {tf_name}: {stats['signals'][tf_name]} signals")
    
    print("\n3. TRADES EXECUTED:")
    for tf_name in ['1h', '15m', '5m', '1m']:
        trades = stats['trades'][tf_name]
        wins = stats['wins'][tf_name]
        win_rate = (wins / trades * 100) if trades > 0 else 0
        print(f"  {tf_name}: {trades} trades, {wins} wins, {win_rate:.1f}% win rate")
    
    print("\n4. HTF -> LTF TRANSITIONS:")
    for transition, counts in stats['htf_ltf_transitions'].items():
        print(f"  {transition}: UP={counts['UP']}, DOWN={counts['DOWN']}")
    
    return stats


def load_candles(tf, limit):
    rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'BTCUSDT_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


def is_kill_zone(candle: Candle) -> bool:
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(candle.time / 1000, tz=timezone.utc)
    ny_hour = (dt.hour - 4) % 24
    KILL_ZONES = {"london": (2, 5), "ny_am": (7, 10), "silver_bullet": (10, 11)}
    for zone_name, (start, end) in {"london": (2, 5), "ny_am": (7, 10), "silver_bullet": (10, 11)}.items():
        if start <= (dt.hour - 4) % 24 < end:
            return True
    return False


def is_avoid_session(candle: Candle) -> bool:
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(candle.time / 1000, tz=timezone.utc)
    ny_hour = (dt.hour - 4) % 24
    AVOID_SESSIONS = {"ny_lunch": (12, 13), "asian_range": (20, 24)}
    for session_name, (start, end) in {"ny_lunch": (12, 13), "asian_range": (20, 24)}.items():
        if start <= (dt.hour - 4) % 24 < end:
            return True
    return False


if __name__ == "__main__":
    print("Loading data (this may take a moment)...")
    tf_1d = load_candles('1d', 1000)
    tf_4h = load_candles('4h', 2000)
    tf_1h = load_candles('1h', 8000)
    tf_15m = load_candles('15m', 20000)
    tf_5m = load_candles('5m', 100000)
    tf_1m = load_candles('1m', 300000)
    
    print(f"Loaded all timeframes")
    
    # Add required imports
    import sys
    sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')
    from engine.signal import htf_bias, generate_signal, is_kill_zone, is_avoid_session
    from paper.journal import Engine
    
    # Run the hierarchy test
    stats = run_hierarchy_test(tf_1d, tf_4h, tf_1h, tf_15m, tf_5m, tf_1m)
    
    print("\n" + "=" * 80)
    print("FULL HIERARCHY TEST COMPLETE")
    print("=" * 80)