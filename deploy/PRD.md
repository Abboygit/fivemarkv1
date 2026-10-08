# Five Mark V1 — ICT V2 Trading System: PRD + Code Review

**Version:** P0-sprint-complete · **Date:** 2026-10-08 · **Status:** Paper-forward ready
**Backtest (best config):** 97 trades/yr, 43.3% win, **+0.117 avg R** · **Tests:** 22/22 pass

---

## 1. Product Overview

Five Mark V1 is a **paper-trading-only** ICT (Inner Circle Trader) algorithmic system for
crypto perpetual futures. It generates signals from institutional order-flow concepts
(displacement, liquidity sweep, FVG/OB/Breaker), executes them in a simulated journal with
realistic costs, shows everything on a real-time Canvas dashboard, and pushes trade alerts
to Telegram. **No live orders exist anywhere in the codebase — by design.**

### Goals
- G1. Positive-expectancy paper system on 5m entries gated by 1h bias (BTC/ETH/SOL/ARB).
- G2. Every number reproducible: no-lookahead backtests, regression-locked.
- G3. One-command local run; systemd VPS run; Telegram alerts on every fill.
- G4. Measure everything (MFE/MAE per trade, per-setup events) so exits can be calibrated.

### Non-goals (explicitly out of scope)
- NG1. Live order execution (no exchange keys, no order code, never).
- NG2. Avg R > 0.5 in this sprint (needs entry-quality work — §9).
- NG3. Multi-symbol live dashboard (live tracks **BTCUSDT only**; backtest covers 4 symbols).
- NG4. ML / regime detection (logged for later; not implemented).

---

## 2. Architecture & Data Flow

```
┌──────────────┐  Binance REST   ┌────────────────┐  truncated [:i+1]  ┌──────────────────┐
│ DATA LAYER   │ ──────────────▶ │ SIGNAL ENGINE  │ ─────────────────▶ │ PAPER ENGINE     │
│ history.py   │  12 TFs, 1yr    │ signal.py      │  Signal(...)       │ journal.py       │
│ 4 sym × 12TF │  ~300MB CSV     │ 1h bias → 5m   │  entry/stop/target │ $10k, 1% risk    │
│ forward-fill │  validate_candle│ zones+FVG/OB/  │  rr, event, conf   │ OTE wait/fallback│
└──────────────┘                 │ Breaker/Unicorn│                    │ trail/MFE-lock   │
                                 │ SB 3-step tag  │                    │ MFE/MAE logging  │
                                 └────────────────┘                    └────────┬─────────┘
                                        ▲                                     │ notify
                                        │ bias                                ▼
                                 ┌────────────────┐                   ┌──────────────────┐
                                 │ htf_bias (1h)  │                   │ TELEGRAM BOT     │
                                 │ MSS/BOS+displ. │                   │ entry/exit/P&L,  │
                                 │ 30m fallback   │                   │ /last, /status   │
                                 └────────────────┘                   └──────────────────┘
┌──────────────┐  20s refresh     ┌────────────────┐  WebSocket+REST   ┌──────────────────┐
│ BINANCE LIVE │ ──────────────▶ │ DASHBOARD      │ ─────────────────▶ │ BROWSER (Canvas) │
│ klines/depth │  ltf/htf + 12TF │ server.py:8091 │  /api/state|chart  │ 60fps, DOM/Whale │
│ aggTrades    │  strip (10 bars)│ refresh_once() │  /api/history      │ VPVR/zones/pools │
└──────────────┘                 │ ENGINE.on_candle│  /health           │ replay + drawing │
                                 └────────────────┘                    └──────────────────┘
```

**Trade lifecycle:** `fetch klines → htf_bias → generate_signal → ENGINE.queue →
on_candle (OTE wait ≤3 → entry) → MFE/MAE + stages → exit (stop/target/time) →
_close (pnl, R, copy) → Telegram → dashboard STATE`.

---

## 3. Component Specs

### 3.1 Signal Engine (`src/engine/signal.py`, ~700 lines)

| Item | Spec |
|---|---|
| Entry TF / Bias TF | 5m entries gated by 1h `htf_bias` (UP/DOWN/WAIT); WAIT blocks all |
| Displacement | Body ≥ 0.5×ATR **and** range ≥ 0.8×ATR (`DISP_ATR`, `DISP_RANGE_ATR`) |
| Trigger | Sweep **OR** MSS/BOS at displacement candle `ev` (scanned back `LOOKBACK=12`) |
| Zones (priority) | 1.UNICORN (Breaker∩FVG overlap) 2.BREAKER 3.HIDDEN_OB 4.BPR 5.FVG/OB |
| Retrace gate | Current candle must overlap zone **and** OTE 45–88% Fib (`OTE_FIB_LOW/HIGH`) |
| Premium/Discount veto | Longs blocked in premium, shorts in discount (60-bar hi/lo, buffer 0.08) |
| Session gates | Kill zones ON (`USE_KILL_ZONES`): London 2–5, NY 7–10, Silver Bullet 10–11 (NY). Avoid: lunch 12–13, Asian 20–24 |
| Flow gates | Volume ≥ 1.5× 20-bar avg; ADX > 10 |
| Stop/Target | Nearest swing (stop), first swing ≥ 3.0R (`RISK_REWARD=3.0`); DOL extension to liquidity pool; stop dist within 0.05%–3% of entry and ≥ 1.0×ATR |
| Silver Bullet tag | Sweep-before-displacement ≤12 bars + kill zone → `event="silver_bullet"`, +0.15 conf, `SB:` reason |
| Unicorn | Breaker∩FVG overlap zone (tighter box), +0.1 conf, `event="unicorn"` |
| No-lookahead | FVG reads `ev+1` → guarded by `ev < index` (both call sites); all other reads ≤ index |
| Output | `Signal(side, entry=close, stop, target, rr, reason, event, index, confidence, zone_kind, zone_high/low, sweep_price, event_index)` |

### 3.2 Paper Engine (`src/paper/journal.py`, ~360 lines)

| Item | Spec |
|---|---|
| Capital/costs | $10,000 · 1% risk/trade · 0.04% fee · 1bp slippage (adverse both sides) · max notional 2× equity |
| Capacity | 1 open per timeframe, 5 total (`MAX_OPEN`); queue drops when full |
| Entry | OTE band (62–79% of signal risk dist) touched → limit-style fill inside band; else wait ≤3 candles → market fallback at close. OTE = half size + stop locked to `signal.stop`; fallback = full size, distances re-based on actual entry |
| Geometry guard | Invalid side (stop/target crossed) → skip + `invalid_skipped` counter (backtest: **0**) |
| MFE/MAE | Tracked every candle vs **fixed** `risk_dist` (entry risk); reported per trade + `avg_mfe/avg_mae/capture_rate` in `summary()` |
| Exit stages | ① BE@2.0R **OFF** ② 25%-partial@2.8R **OFF** ③ giveback-trail@2.5R/20% **ON** ④ MFE-lock@5R→50% peak **ON**. (A/B: BE/partial always cut avg R — §7) |
| Intrabar rules | **Stop-first** on ambiguous candles · gap-through-stop/target fills at **open** (not stop/target) · trailing/MFE-lock updates apply **at close** (next-candle effective) · time exit at 60 bars |
| Journal | Every close → `closed[]` + `copy[]` dict (id, setup, result, r, reason, mfe_r, mae_r, partial_r) → Telegram |

### 3.3 Dashboard (`src/dashboard/server.py`, :8091)

Single-symbol live (**BTCUSDT**): 20s `refresh_once()` → klines (5m/1h + 12-TF strip) →
validate → bias (30m fallback) → signal/scan note → `ENGINE.on_candle` → paper summary,
equity curve, last-20 closed trades → DOM depth + $25k+ whale prints → chart candles +
`generate_signal` markers + zones/pools. Serves Canvas SPA + `/api/state|chart|history|
tick|footprint`, `/health`. Fail-soft: any exception → `ok:false` + message, never black screen.

### 3.4 Telegram (`src/paper/telegram_bot.py` + hooks in `journal.py`)

Env-gated (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, else silently off). Entry alert
(side/entry/stop/target/risk/RR/setup) on every open; exit alert (entry→exit, $P&L, R,
reason, bars, MFE/MAE, partial R) on every close; `/last`, `/status` polling commands.

### 3.5 Backtest (`final_backtest.py`, `backtest_v2.py`)

Walks 5m candles (~100k/symbol), aligns 1h bias, calls `generate_signal(ltf[:i+1], i)`
(**truncated slice — no lookahead by construction**), queues + steps engine. Prints
per-trade lines + aggregate. ~2–4 min for 4 symbols.

---

## 4. Configuration Reference (shipped best config)

```python
# signal.py
RISK_REWARD = 3.0 · LOOKBACK = 12 · DISP_ATR = 0.5 · DISP_RANGE_ATR = 0.8
MIN_STOP_ATR_MULT = 1.0 · VOLUME_MULT = 1.5 · ADX_THRESHOLD = 10
USE_KILL_ZONES = True · SESSION_FILTER_ENABLED = True
OTE_FIB_LOW/HIGH = 0.45/0.88 · SILVER_BULLET_LOOKBACK = 12
# journal.py
RISK_PCT = 0.01 · FEE_RATE = 0.0004 · SLIPPAGE_BPS = 1.0 · MAX_BARS = 60 · MAX_OPEN = 5
TRAILING_ACTIVATION_R = 2.5 · TRAILING_GIVEBACK = 0.2
BE_ACTIVATION_R = 999.0 (OFF) · PARTIAL_ACTIVATION_R = 999.0 (OFF, fraction 0.25)
MFE_LOCK_ACTIVATION_R = 5.0 · MFE_LOCK_FRACTION = 0.5
```

---

## 5. Correctness Guarantees (regression-locked, 22/22 green)

| Guarantee | Test | Where |
|---|---|---|
| No lookahead: `signal(i)` identical on full vs `[:i+1]` (trend up/down × UP/DOWN/BOTH) | `test_no_lookahead_full_vs_truncated` | test_regression.py |
| Next-bar fill: waits on no-dip candles; fallback fills at that candle's close | `test_next_bar_fill_never_signal_close` | test_regression.py |
| Gap-through-stop fills at open (slipped), never stop price | `test_gap_through_stop_fills_at_open` | test_regression.py |
| Stop-first on ambiguous candles | `test_stop_wins_tie_when_both_hit` (+ test_paper.py duplicate) | test_regression.py |
| MFE/MAE tracked + in copy/summary | `test_mfe_mae_tracked_and_reported` | test_regression.py |
| Entry timing, target/stop exits, one-open-per-TF, OTE wait+fallback | 5 tests | test_paper.py |
| Bias values, WAIT-blocks, RR≥2.5 + geometry invariant, helper shapes | 12 tests | test_signal.py |

---

## 6. Code Review Findings (this sprint)

### Fixed bugs
1. **FVG future-read (lookahead):** `_fvg_zone(candles, ev)` reads `ev+1`; at `ev==index`
   that candle doesn't exist yet in live trading. Guarded both call sites
   (Priority-4 + Unicorn) with `ev < index`. Backtests were safe (truncated slices);
   **live dashboard (`generate_signal(ltf, len-1)` on full array) was exposed — now fixed.**
2. **Short-trailing never initialized:** `lowest_price=0.0` + `c.low < lowest_price`
   could never fire on first activation. Peak now initialized at activation for both sides.
3. **Same-candle trailing leapfrog:** giveback stop computed from candle high could exceed
   target and get hit by the same candle's low. Trailing/MFE-lock updates now apply at
   close (next-candle effective); BE/partial stay pre-check (near-entry, can't leapfrog).
4. **Gap fills:** stops filled at stop price even when gapped through — now fill at open.
5. **RISK_REWARD drift:** found 3.5 (stale edit), restored to validated 3.0.

### Tech debt (works, improve later)
- T1. Telegram creates a new `asyncio.run()` loop per alert (fine at ~100 trades/yr;
  move to persistent session + queue if alert volume grows; will crash if journal ever
  runs inside a running event loop — dashboard is sync today).
- T2. `BE/PARTIAL_*=999.0` disables via unreachable threshold — explicit but magic;
  prefer `BE_ENABLED=False`-style flags on next touch.
- T3. Backtest `ltf[:i+1]` slicing is O(n²) copies (~100k slices/symbol); fine at this
  scale, switch to index-bounded access if symbols/timeframes grow.
- T4. Dashboard `refresh_once` runs ~360 `generate_signal` calls (chart markers) every
  20s — heaviest VPS cost; cache markers per closed candle.
- T5. `bars_held` increments per dashboard refresh, not per candle (time-exit is
  wall-clock-ish live). Backtest is exact; live drifts. Standardize on candle-close counting.
- T6. Minor: unused `is_sb` variable; duplicate `HIDDEN_OB` key in `event_map`;
  wrong `_sweep() -> str | None` annotation (returns dict — test asserts dict).

### Design observations (not bugs)
- O1. Live dashboard is **single-symbol (BTCUSDT)**; multi-symbol exists only in backtest.
  Chart history file is hardcoded to `BTCUSDT_{tf}.json`.
- O2. Partial fills at `c.close` even if the same candle also stops out — accepted paper fuzz.
- O3. OTE journal band (62–79% of signal risk) differs from signal OTE_FIB (45–88% of
  swing) — two different OTE definitions stacked; works, but document before tuning either.
- O4. Win rate and avg R trade off mechanically (BE/partial A/B); edge lives in runners.

---

## 7. A/B Evidence (each: full 4-symbol backtest)

| Config | Trades | Win% | Avg R | Verdict |
|---|---|---|---|---|
| Trail 2.5R/20% only (baseline) | 98 | 48.0% | +0.125 | baseline |
| +BE@2.0 +partial50%@2.5 | 97 | 58.8% | +0.035 | ❌ kills runners |
| +BE@2.2 +partial25%@2.8 | 97 | 54.6% | +0.035 | ❌ same |
| BE/partial OFF +MFE-lock (shipped) | 97 | 43.3% | **+0.117** | ✅ ≈ baseline + infra |

Measured MFE ≈ 2.0–2.8R avg vs capture ≈ 1.5% → upside exists in entries; no tested
exit variant harvests it. **Conclusion: +0.5 avg R needs entry quality, not exit tuning.**

---

## 8. Operations Runbook

### Local
```bash
cd deploy
python -m pytest tests -q        # 22/22 expected
python final_backtest.py          # ~2-4 min, 4 symbols
python run_server.py              # http://127.0.0.1:8091  (PORT in server.py; 8090 was taken)
```

### Telegram setup
```bash
# 1. @BotFather → /newbot → TOKEN; @userinfobot → CHAT_ID
export TELEGRAM_BOT_TOKEN="..." TELEGRAM_CHAT_ID="..."
pip install python-telegram-bot
python -m src.paper.telegram_bot  # polling test (/last, /status)
```

### VPS (systemd)
```ini
# /etc/systemd/system/fivemark.service
[Unit] Description=Five Mark V1  After=network.target
[Service] Type=simple  User=ubuntu  WorkingDirectory=/opt/fivemark/deploy
Environment=TELEGRAM_BOT_TOKEN=...  Environment=TELEGRAM_CHAT_ID=...
ExecStart=/opt/fivemark/venv/bin/python run_server.py  Restart=always  RestartSec=10
[Install] WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now fivemark
sudo journalctl -u fivemark -f
```
**Env-before-import:** Telegram reads env at `journal.py` import; systemd
`Environment=` lines satisfy this. Changing env needs `systemctl restart`.

### Verify after deploy
1. `curl localhost:8091/health` → `{"ok": true/false, ...}` (`ok:false` + `updated_at:0` = still loading).
2. Open dashboard → Canvas renders, TF strip fills within ~1 min.
3. Send test Telegram: trigger polling module once.
4. Paper-forward for 1 week before any capital discussion.

---

## 9. Roadmap

**P1 (entry quality — the +0.5 path):** 15m MTF confirmation (1h bias → 15m structure →
5m trigger); per-setup MFE calibration (SB/unicorn/fvg/OB) once N≥50/setup; displacement
v3 (velocity + range-expansion scoring); 10–20 symbols for 200–400 trades/yr.
**Hardening:** T4 marker cache, T5 bar-based time exit, T1 persistent Telegram session,
Deflated-Sharpe + walk-forward validation gate, drawdown circuit breaker (-25% → 7d pause).
**Out of scope:** live execution (never).

---

## 10. Acceptance Status

| Criterion | Status |
|---|---|
| 22/22 tests incl. 5 honesty regressions | ✅ |
| Backtest positive expectancy (+0.117, 97 trades) | ✅ |
| No-lookahead (guard + test + truncated pipeline) | ✅ |
| Dashboard renders (Playwright: Canvas found) | ✅ |
| Telegram entry/exit/P&L + /last | ✅ (env-gated) |
| Notion docs current | ✅ |
| Avg R > 0.5 | ❌ → P1 entry-quality work |
| VPS 1-week forward | 🔄 pending deploy |
