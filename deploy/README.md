# Five Mark V1 — ICT V2 Trading System

Production-ready ICT V2 signal engine with paper trading, live dashboard, and 12-timeframe data pipeline.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download 1yr history (12 timeframes) — runs once, then incremental
python -m src.market.history

# 3. Run backtest (no look-ahead, per-candle aligned bias)
python backtest_v2.py

# 4. Start live dashboard (port 8091)
python run_server.py
# Open http://127.0.0.1:8091
```

## Features

- **ICT V2 Signal Engine**: HTF bias (1h) → LTF entry (5m) with sweep+struct mandatory, displacement, FVG/OB zones, RR≥2.5
- **No Look-Ahead**: Per-candle aligned HTF bias via time-index mapping
- **Paper Trading**: $10k, 1% risk, 0.04% fee, 1bps slippage, stop-first, 60-bar timeout
- **Dashboard**: Canvas 60fps, 12-TF live strip, DOM/whale prints, VPVR, zones/pools, pan/zoom/GO LIVE
- **Data Pipeline**: 1yr/12TF Binance Futures, auto-forward-fill on restart

## Project Structure

```
├── src/
│   ├── engine/
│   │   ├── signal.py      # ICT V2 core (generate_signal, htf_bias, zones, pools)
│   │   ├── primitives.py  # atr, swings, fvg detection
│   │   └── __init__.py
│   ├── paper/
│   │   ├── journal.py     # PaperEngine (queue, on_candle, summary)
│   │   └── __init__.py
│   ├── market/
│   │   ├── binance.py     # fetch_klines, Candle dataclass
│   │   ├── history.py     # 1yr/12TF downloader + forward_fill
│   │   ├── validator.py   # candle validation
│   │   └── __init__.py
│   ├── dashboard/
│   │   └── server.py      # ThreadedHTTPServer, Canvas chart, ICT layers
│   └── __init__.py
├── tests/                  # 16 passing tests
├── data/                   # 12 TFs JSON (auto-downloaded)
├── requirements.txt
├── run_server.py           # starts dashboard on :8091
└── .gitignore
```

## Backtest

```bash
python backtest_v2.py           # full look-ahead-free backtest
python backtest_v2.py --no-ct   # without counter-trend (same now)
```

## Live Dashboard

```bash
python run_server.py
# http://127.0.0.1:8091
```

- Canvas 60fps chart with ICT overlays (zones, pools, marks, DOM, whale prints)
- Pan/zoom/drag, GO LIVE, GO REAL-TIME, replay mode
- 12-TF live strip, VPVR, session shading, light/dark theme

## Configuration

Edit `src/engine/signal.py` constants:
```python
DISP_ATR = 1.0           # displacement body threshold
DISP_RANGE_ATR = 1.3     # displacement range threshold
RISK_REWARD = 2.5        # minimum RR
LOOKBACK = 18            # displacement lookback
MIN_STOP_ATR_MULT = 1.5  # minimum stop distance
```

## Tests

```bash
pytest tests/ -q
```

## VPS Deployment

```bash
# On VPS (Ubuntu/Debian)
sudo apt update && sudo apt install python3 python3-pip python3-venv
git clone <repo>
cd five-mark-v1
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m src.market.history      # initial download (~15 min)
nohup python run_server.py > server.log 2>&1 &
```

- Dashboard: `http://<vps-ip>:8091` (bind 0.0.0.0:8091 in production, use nginx + SSL)
- For HTTPS: put behind nginx/Caddy with Let's Encrypt

## Live Trading Readiness

**Current Status: NOT READY FOR REAL CAPITAL**

| Metric | Value | Status |
|--------|-------|--------|
| Win Rate | 40% | ⚠️ |
| Avg R | -0.23 | ❌ Negative edge |
| Trades/52d | 25 | Low frequency |

**Blockers for Live:**
1. Negative expectancy (-0.23 avg R) — will lose money
2. No alerting/monitoring
3. No real execution adapter (paper only)
3. No position reconciliation

**Next Levers to Try:**
1. Mandatory sweep+struct (done)
2. RR target 3.0
3. Volatility filter (ATR percentile)
4. Trend strength filter (ADX)