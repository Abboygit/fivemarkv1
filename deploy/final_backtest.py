#!/usr/bin/env python3
"""
Final Multi-Symbol Backtest - 5m timeframe with 1h bias gating
Tests BTC, ETH, SOL, ARB on 5m timeframe with 1h bias gating
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

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT"]
N_5M = 100000

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


def run_symbol_backtest(symbol, limit_5m=100000):
    ltf = load_candles(symbol, '5m', limit_5m)[:-1]
    htf = load_candles(symbol, '1h', 9000)[:-1]
    
    if not ltf or not htf:
        return None
    
    e = Engine()
    j = 0
    n_sig = 0
    
    for i in range(40, len(ltf)):
        while j + 1 < len(htf) and htf[j + 1].time <= ltf[i].time:
            j += 1
        if htf[j].time > ltf[i].time:
            continue
        htf_slice = htf[:j + 1]
        bias = htf_bias(htf, j)
        if bias == 'WAIT':
            continue
        pb = pullback_pct(htf, j)
        sig = generate_signal(ltf[:i + 1], i, bias=bias)
        if sig:
            e.queue(sig, '5m')
        e.on_candle('5m', ltf[i], 5 * 60 * 1000)
    
    s = e.summary()
    return {
        'symbol': symbol,
        'trades': s['closed'],
        'wins': s['wins'],
        'win_rate': s['win_rate'],
        'avg_r': s.get('avg_r', 0),
        'equity': s['equity'],
        'net_r': sum(t.r_multiple for t in e.closed) if e.closed else 0,
        'trades_list': e.closed
    }


def run_multi_symbol_backtest():
    print("=" * 80)
    print("MULTI-SYMBOL BACKTEST: 5m timeframe with 1h bias gating")
    print("=" * 80)
    
    all_results = {}
    
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT"]:
        print(f"\n{'='*80}")
        print(f"Testing {symbol}...")
        print("=" * 80)
        
        result = run_symbol_backtest(symbol)
        if result is None:
            print(f"  No data available for {symbol}")
            continue
            
        print(f"\n  Results for {symbol}:")
        print(f"  Trades: {result['trades']}, Wins: {result['wins']}, Win%: {result['win_rate']:.1f}%")
        print(f"  Avg R: {result['avg_r']:.3f}, Equity: ${result['equity']:.2f}, Net R: {result['net_r']:.2f}")
        
        if result['trades_list']:
            print(f"  Trade details:")
            for t in result['trades_list']:
                print(f"    {t.id} {t.side} entry={t.entry:.1f} stop={t.stop:.1f} target={t.target:.1f} "
                      f"exit={t.exit:.1f} reason={t.exit_reason} R={t.r_multiple:.2f}")
        
        all_results[symbol] = result
    
    # Aggregate results
    print("\n" + "=" * 80)
    print("AGGREGATE RESULTS (ALL SYMBOLS)")
    print("=" * 80)
    
    total_trades = total_wins = 0
    
    for tf_name in ['5m']:
        tf_trades = sum(all_results[s]['trades'] for s in SYMBOLS if s in all_results)
        tf_wins = sum(all_results[s]['wins'] for s in SYMBOLS if s in all_results)
        win_rate = (tf_wins / tf_trades * 100) if tf_trades > 0 else 0
        avg_r = sum(all_results[s]['avg_r'] for s in SYMBOLS if s in all_results) / len([s for s in SYMBOLS if s in all_results])
        print(f"  5m: {tf_trades} trades, {tf_wins} wins, {win_rate:.1f}% win, avg R: {avg_r:.3f}")
        total_trades += tf_trades
        total_wins += tf_wins
    
    overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    print(f"\n  TOTAL: {total_trades} trades, {total_wins} wins, {overall_wr:.1f}% win rate")


if __name__ == "__main__":
    run_multi_symbol_backtest()