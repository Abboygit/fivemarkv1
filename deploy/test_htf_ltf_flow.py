#!/usr/bin/env python3
"""
HTF → LTF Flow Test
Verifies the complete HTF bias → LTF signal pipeline works correctly.
Tests each stage: 1h bias → 5m pullback → signal generation.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src')

from market.binance import Candle
from engine.signal import htf_bias, pullback_pct, generate_signal, _displacement, _sweep, _mss_or_bos, _fvg_zone, _ob_zone

DATA_DIR = Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data')


def load_candles(tf, limit):
    rows = json.loads((Path(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\data') / f'BTCUSDT_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


def test_htf_bias_stages():
    """Test each stage of HTF bias calculation."""
    print("=" * 60)
    print("TEST 1: HTF Bias Stages")
    print("=" * 60)
    
    htf = load_candles('1h', 200)[:-1]
    idx = len(htf) - 1
    
    # Stage 1: Primary trend (50-candle)
    if idx >= 50:
        if htf[idx].close > htf[idx-49].close * 1.001:
            primary = "UP"
        elif htf[idx].close < htf[idx-49].close * 0.999:
            primary = "DOWN"
        else:
            primary = "WAIT"
    else:
        primary = "WAIT"
    print(f"  Primary trend (50-candle): {primary}")
    
    # Stage 2: Structure (swing highs/lows)
    from engine.primitives import confirmed_swings
    swings = confirmed_swings(htf, idx)
    highs = [s.price for s in swings if s.side == "high"]
    lows = [s.price for s in swings if s.side == "low"]
    up_struct = len(highs) >= 2 and len(lows) >= 2 and highs[-1] > highs[-2] and lows[-1] > lows[-2]
    down_struct = len(highs) >= 2 and len(lows) >= 2 and highs[-1] < highs[-2] and lows[-1] < lows[-2]
    print(f"  Structure UP: {up_struct}, DOWN: {down_struct}")
    
    # Stage 3: Premium/Discount
    from engine.signal import _premium_discount
    start = max(0, idx - 59)
    window = htf[start:idx+1]
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    pd = _premium_discount(htf[idx].close, hi, lo)
    print(f"  Premium/Discount: {pd}")
    
    # Final bias
    bias = htf_bias(htf, idx)
    print(f"  FINAL BIAS: {bias}")
    return bias


def test_pullback_calculation():
    """Test pullback percentage calculation."""
    print("\n" + "=" * 60)
    print("TEST 2: Pullback Calculation")
    print("=" * 60)
    
    htf = load_candles('1h', 200)[:-1]
    idx = len(htf) - 1
    
    pb = pullback_pct(htf, idx)
    hi_60 = max(c.high for c in htf[max(0, idx-59):idx+1])
    curr_close = htf[idx].close
    expected = (hi_60 - curr_close) / hi_60
    
    print(f"  Current close: {curr_close:.1f}")
    print(f"  60-candle high: {hi_60:.1f}")
    print(f"  Pullback %: {pb*100:.2f}% (expected: {expected*100:.2f}%)")
    print(f"  Match: {abs(pb - expected) < 1e-9}")


def test_signal_generation_step_by_step():
    """Test LTF signal generation with HTF bias at specific candle."""
    print("\n" + "=" * 60)
    print("TEST 3: LTF Signal Generation (Step by Step)")
    print("=" * 60)
    
    ltf = load_candles('5m', 500)[:-1]
    htf = load_candles('1h', 500)[:-1]
    
    # Test at a specific candle where we expect a signal
    test_idx = 100
    
    # Get HTF bias at that time
    htf_idx = 0
    while htf_idx + 1 < len(htf) and htf[htf_idx + 1].time <= ltf[test_idx].time:
        htf_idx += 1
    
    bias = htf_bias(htf[:htf_idx+1], htf_idx)
    pb = pullback_pct(htf[:htf_idx+1], htf_idx)
    
    print(f"  LTF index: {test_idx}, time: {ltf[test_idx].time}")
    print(f"  HTF index: {htf_idx}, bias: {bias}, pullback: {pullback_pct(htf[:htf_idx+1], htf_idx)*100:.2f}%")
    
    # Step through signal generation
    cur = ltf[test_idx]
    print(f"  Current candle: O={cur.open:.1f} H={cur.high:.1f} L={cur.low:.1f} C={cur.close:.1f}")
    
    LOOKBACK = 18
    found_signal = False
    for ev in range(test_idx, max(test_idx - 18, 0) - 1, -1):
        direction = _displacement(ltf, ev)
        if not direction:
            continue
        
        sweep = _sweep(ltf, ev)
        struct = _mss_or_bos(ltf, ev, direction)
        if not sweep and not struct:
            continue
        
        zone = _fvg_zone(ltf, ev, direction) or _ob_zone(ltf, ev, direction)
        if not zone or zone["index"] >= test_idx:
            continue
        
        cur_candle = ltf[test_idx]
        overlap = cur_candle.low <= zone["high"] and cur_candle.high >= zone["low"]
        if not overlap:
            continue
        
        side = "long" if direction == "bullish" else "short"
        
        # HTF Gate
        if bias == "UP" and side != "long":
            print(f"  ev={ev}: {direction} blocked by UP bias")
            continue
        if bias == "DOWN" and side != "short":
            print(f"  ev={ev}: {direction} blocked by DOWN bias")
            continue
        if bias == "WAIT":
            print(f"  ev={ev}: blocked by WAIT bias")
            continue
        
        # Premium/Discount
        start = max(0, test_idx - 59)
        hi = max(c.high for c in ltf[start:test_idx+1])
        lo = min(c.low for c in ltf[start:test_idx+1])
        from engine.signal import _premium_discount
        pd = _premium_discount(cur.close, hi, lo)
        if side == "long" and pd == "premium":
            print(f"  ev={ev}: long blocked by premium")
            continue
        if side == "short" and pd == "discount":
            print(f"  ev={ev}: short blocked by discount")
            continue
        
        # Stops/Targets
        from engine.primitives import confirmed_swings
        swings = confirmed_swings(ltf[:test_idx+1], test_idx)
        entry = cur.close
        if side == "long":
            stops = sorted([s.price for s in swings if s.side == "low" and s.price < entry], key=lambda p: entry - p)
            targets = sorted([s.price for s in swings if s.side == "high" and s.price > entry])
        else:
            stops = sorted([s.price for s in swings if s.side == "high" and s.price > entry], key=lambda p: p - entry)
            targets = sorted([s.price for s in swings if s.side == "low" and s.price < entry])
        
        if not stops or not targets:
            continue
        
        stop = stops[0]
        dist = abs(entry - stop)
        if not (entry * 0.0005 <= dist <= entry * 0.03):
            continue
        
        from engine.primitives import atr
        atr_val = atr(ltf[:test_idx+1], test_idx)
        if dist < atr_val * 1.5:
            continue
        
        target = None
        for t in targets:
            if abs(t - entry) >= dist * 2.5:
                target = t
                break
        if target is None:
            continue
        
        print(f"\n  ✓ SIGNAL FOUND at ev={ev}:")
        print(f"    side={side}, entry={entry:.1f}, stop={stop:.1f}, target={target:.1f}")
        print(f"    dist={dist:.1f}, R={abs(target-entry)/dist:.2f}")
        print(f"    zone={zone['kind']}, sweep={sweep}, struct={struct}")
        found_signal = True
        break
    
    if not found_signal:
        print("  [X] No signal found at this index")


def test_full_pipeline():
    """Test complete pipeline: 1h bias -> 5m signal -> paper execution"""
    print("\n" + "=" * 60)
    print("TEST 4: Full Pipeline (1h -> 5m -> Paper)")
    print("=" * 60)
    
    from paper.journal import Engine
    from engine.signal import generate_signal, htf_bias, pullback_pct
    
    ltf = load_candles('5m', 2000)[:-1]
    htf = load_candles('1h', 2000)[:-1]
    
    e = Engine()
    htf_idx = 0
    signals = 0
    trades = 0
    
    for i in range(40, min(2000, len(ltf))):
        # Align HTF
        while htf_idx + 1 < len(htf) and htf[htf_idx + 1].time <= ltf[i].time:
            htf_idx += 1
        
        if htf[htf_idx].time > ltf[i].time:
            continue
            
        htf_now = htf[:htf_idx+1]
        bias = htf_bias(htf_now, htf_idx)
        pb = pullback_pct(htf_now, htf_idx)
        
        sig = generate_signal(ltf[:i+1], i, bias=bias)
        if sig:
            print(f"  i={i} SIGNAL: {sig.side} entry={sig.entry:.1f} stop={sig.stop:.1f} target={sig.target:.1f} RR={sig.rr:.2f} zone={sig.zone_kind}")
            e.queue(sig, '5m')
        
        e.on_candle('5m', ltf[i], 5*60*1000)
    
    s = e.summary()
    print(f"\n  Total trades: {s['closed']}, Wins: {s['wins']}, Win rate: {s['win_rate']}%")
    print(f"  Equity: ${s['equity']:.2f}, Avg R: {s.get('avg_r', 0)}")


if __name__ == "__main__":
    test_htf_bias_stages()
    test_pullback_calculation()
    test_signal_generation_step_by_step()
    test_full_pipeline()
    print("\n" + "=" * 60)
    print("ALL HTF->LTF FLOW TESTS COMPLETE")
    print("=" * 60)