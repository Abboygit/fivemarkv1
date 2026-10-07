#!/usr/bin/env python3
"""
Multi-Symbol Comprehensive Backtest
Tests BTC, ETH, SOL, ARB with parallel timeframe tracks:
- 1d → 4h → 1h → 15m → 5m → 1m
Captures HTF buy signals and maps to LTF short-term trades
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

def load_candles(symbol, tf, limit):
    rows = json.loads((DATA_DIR / f'{symbol}_{tf}.json').read_text())
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), 
                          low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


class MultiSymbolEngine:
    def __init__(self, symbol):
        self.symbol = symbol
        self.engines = {tf: Engine() for tf in ["1h", "15m", "5m", "1m"]}
        self.stats = {
            'signals': {'1h': 0, '15m': 0, '5m': 0, '1m': 0},
            'trades': {'1h': 0, '15m': 0, '5m': 0, '1m': 0},
            'wins': {'1h': 0, '15m': 0, '5m': 0, '1m': 0},
            'htf_ltf': {
                '1d_to_4h': {'UP': 0, 'DOWN': 0},
                '4h_to_1h': {'UP': 0, 'DOWN': 0},
                '1h_to_15m': {'UP': 0, 'DOWN': 0},
                '15m_to_5m': {'UP': 0, 'DOWN': 0},
                '5m_to_1m': {'UP': 0, 'DOWN': 0},
            },
            'htf_buy_capture': [],  # Track HTF buy signals
            'htf_buy_to_ltf': []    # HTF buy -> LTF trade mapping
        }
    
    def run(self, tf_data):
        """Run backtest for this symbol"""
        tf_1d = tf_data['1d']
        tf_4h = tf_data['4h']
        tf_1h = tf_data['1h']
        tf_15m = tf_data['15m']
        tf_5m = tf_data['5m']
        tf_1m = tf_data['1m']
        
        idx_1d = idx_4h = idx_1h = idx_15m = idx_5m = idx_1m = 0
        
        # Pre-calculate 1h bias for 15m signals
        # We'll compute on the fly
        
        for i_1m in range(40, len(tf_1m)):
            # Align 1h to 1m
            while idx_1h + 1 < len(tf_1h) and tf_1h[idx_1h + 1].time <= tf_1m[i_1m].time:
                idx_1h += 1
            if idx_1h >= len(tf_1h) or tf_1h[idx_1h].time > tf_1m[i_1m].time:
                continue
            
            # Align 4h to 1h
            while idx_4h + 1 < len(tf_4h) and tf_4h[idx_4h + 1].time <= tf_1h[idx_1h].time:
                idx_4h += 1
            if idx_4h >= len(tf_4h) or tf_4h[idx_4h].time > tf_1h[idx_1h].time:
                continue
            
            # Align 1d to 4h
            while idx_1d + 1 < len(tf_1d) and tf_1d[idx_1d + 1].time <= tf_4h[idx_4h].time:
                idx_1d += 1
            if idx_1d >= len(tf_1d) or tf_1d[idx_1d].time > tf_4h[idx_4h].time:
                continue
            
            # Align 15m to 1h
            while idx_15m + 1 < len(tf_15m) and tf_15m[idx_15m + 1].time <= tf_1h[idx_1h].time:
                idx_15m += 1
            if idx_15m >= len(tf_15m) or tf_15m[idx_15m].time > tf_1h[idx_1h].time:
                continue
            
            # Align 5m to 15m
            while idx_5m + 1 < len(tf_5m) and tf_5m[idx_5m + 1].time <= tf_15m[idx_15m].time:
                idx_5m += 1
            if idx_5m >= len(tf_5m) or tf_5m[idx_5m].time > tf_15m[idx_15m].time:
                continue
            
            # Get biases
            bias_1d = htf_bias(tf_1d[:idx_1d + 1], idx_1d)
            bias_4h = htf_bias(tf_4h[:idx_4h + 1], idx_4h)
            bias_1h = htf_bias(tf_1h[:idx_1h + 1], idx_1h)
            bias_15m = htf_bias(tf_15m[:idx_15m + 1], idx_15m)
            
            # 1h signal (gated by 4h bias)
            sig_1h = generate_signal(tf_1h[:idx_1h + 1], idx_1h, bias=bias_4h, check_kill_zone=False)
            if sig_1h:
                self.engines['1h'].queue(sig_1h, '1h')
            
            # 15m signal (gated by 1h bias)
            sig_15m = generate_signal(tf_15m[:idx_15m + 1], idx_15m, bias=bias_1h, check_kill_zone=False)
            if sig_15m:
                self.engines['15m'].queue(sig_15m, '15m')
            
            # 5m signal (gated by 15m bias)
            sig_5m = generate_signal(tf_5m[:idx_5m + 1], idx_5m, bias=bias_15m, check_kill_zone=False)
            if sig_5m:
                # Capture HTF buy signal mapping to LTF trade
                if bias_15m == 'UP' and sig_5m.side == 'long':
                    self.stats['htf_buy_capture'].append({
                        'symbol': self.symbol,
                        'time': tf_5m[idx_5m].time,
                        'price': tf_5m[idx_5m].close,
                        'htf_bias': bias_15m,
                        'ltf_signal': sig_5m
                    })
                self.engines['5m'].queue(sig_5m, '5m')
            
            # 1m signal (ENTRY timeframe) - apply filters
            if not is_kill_zone(tf_1m[i_1m]) or is_avoid_session(tf_1m[i_1m]):
                self.engines['1m'].on_candle('1m', tf_1m[i_1m], 60000)
                continue
            
            sig_1m = generate_signal(tf_1m[:idx_1m + 1], i_1m, bias=bias_15m, check_kill_zone=True)
            if sig_1m:
                self.engines['1m'].queue(sig_1m, '1m')
            
            # Update all engines
            for tf_name, eng in self.engines.items():
                if tf_name == '1h':
                    eng.on_candle(tf_name, tf_1h[idx_1h], 3600000)
                elif tf_name == '15m':
                    eng.on_candle(tf_name, tf_15m[idx_15m], 900000)
                elif tf_name == '5m':
                    eng.on_candle(tf_name, tf_5m[idx_5m], 300000)
                elif tf_name == '1m':
                    eng.on_candle(tf_name, tf_1m[i_1m], 60000)
    
    def get_summary(self):
        result = {}
        for tf_name, eng in self.engines.items():
            s = eng.summary()
            result[tf_name] = {
                'trades': s['closed'],
                'wins': s['wins'],
                'win_rate': s['win_rate'],
                'avg_r': s['avg_r'],
                'equity': s['equity'],
            }
        return result


def load_candles(symbol, tf, limit):
    try:
        rows = json.loads((DATA_DIR / f'{symbol}_{tf}.json').read_text())
    except:
        return []
    out = []
    for r in rows[-limit:]:
        out.append(Candle(time=r[0], open=float(r[1]), high=float(r[2]), 
                          low=float(r[3]), close=float(r[4]), volume=float(r[5])))
    return out


def run_multi_symbol_backtest():
    print("=" * 80)
    print("MULTI-SYMBOL BACKTEST: BTC, ETH, SOL, ARB")
    print("=" * 80)
    
    all_results = {}
    
    for symbol in SYMBOLS:
        print(f"\n{'='*80}")
        print(f"Testing {symbol}...")
        print("=" * 80)
        
        tf_data = {}
        for tf in TIMEFRAMES:
            limit = 100000 if tf == '1m' else (100000 if tf == '5m' else 
                    (10000 if tf == '15m' else (2000 if tf in ['1h', '4h'] else 1000)))
            tf_data[tf] = load_candles(symbol, tf, limit)
            if not tf_data[tf]:
                print(f"  Warning: No data for {symbol} {tf}")
            else:
                print(f"  {tf}: {len(tf_data[tf])} candles")
        
        engine = MultiSymbolEngine(symbol)
        engine.run(tf_data)
        all_results[symbol] = engine.get_summary()
        
        # Print per-timeframe results
        print(f"\n  Results for {symbol}:")
        for tf_name in ['1h', '15m', '5m', '1m']:
            r = engine.get_summary()[tf_name]
            print(f"  {tf_name}: {r['trades']} trades, {r['win_rate']:.1f}% win, "
                  f"avg R: {r['avg_r']:.3f}, equity: ${r['equity']:.2f}")
    
    # Aggregate all results
    print("\n" + "=" * 80)
    print("AGGREGATE RESULTS (ALL SYMBOLS)")
    print("=" * 80)
    
    total_trades = total_wins = 0
    
    for tf_name in ['1h', '15m', '5m', '1m']:
        tf_trades = sum(all_results[s][tf_name]['trades'] for s in SYMBOLS)
        tf_wins = sum(all_results[s][tf_name]['wins'] for s in SYMBOLS)
        win_rate = (tf_wins / tf_trades * 100) if tf_trades > 0 else 0
        avg_r = sum(all_results[s][tf_name]['avg_r'] for s in SYMBOLS) / len(SYMBOLS)
        print(f"  {tf_name}: {tf_trades} trades, {tf_wins} wins, {win_rate:.1f}% win, avg R: {avg_r:.3f}")
        total_trades += tf_trades
        total_wins += tf_wins
    
    overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    print(f"\n  TOTAL: {total_trades} trades, {total_wins} wins, {overall_wr:.1f}% win rate")


if __name__ == "__main__":
    run_multi_symbol_backtest()