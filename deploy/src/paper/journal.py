"""Paper trading journal — nakli paise, asli hisaab. LIVE ORDER KA ZIKR BAN HAI.

Design: Paper Trading design.md ($10k, 1% risk, agli-candle entry, stop-first).
Seekhne wali copy: har band trade yahin likha jayega (Signal Engine 6B).
"""
import sys
import os
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market.binance import Candle  # noqa: E402

# Telegram notifier (optional)
TELEGRAM_ENABLED = bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
if TELEGRAM_ENABLED:
    try:
        from .telegram_bot import (
            get_notifier, notify_entry_sync, notify_exit_sync, TelegramConfig
        )
        _notifier = get_notifier()
    except Exception as e:
        print(f"Telegram init failed: {e}")
        TELEGRAM_ENABLED = False
else:
    _notifier = None

INITIAL_EQUITY = 10_000.0
RISK_PCT = 0.01
FEE_RATE = 0.0004
SLIPPAGE_BPS = 1.0
MAX_BARS = 60
MAX_OPEN = 5
MAX_NOTIONAL_X = 2.0  # position itni badi nahi ke fee hi kha jaye (backtest #1 ka seekh)

TRAILING_STOP_ENABLED = True
TRAILING_ACTIVATION_R = 2.5  # Stage 3: peak + giveback trail
TRAILING_GIVEBACK = 0.2  # peak gain ka 20% wapas to exit

# 3-stage adaptive trailing (research: Trading Glass / ARG Trade / Inspired)
# Stage 1+2 OFF (A/B: BE@2.0/2.2 + partial 50%@2.5/25%@2.8 sabne avg R giraya,
# win rate ke badle. Edge runners me hai. Machinery rakhi hai, re-enable test karke.)
BE_ACTIVATION_R = 999.0      # Stage 1: stop -> breakeven (+fee buffer)
PARTIAL_ACTIVATION_R = 999.0  # Stage 2: partial (fraction 0.25 rakha — research: chhota partial)
PARTIAL_FRACTION = 0.25
MFE_LOCK_ACTIVATION_R = 5.0  # Stage 4: peak ka 50% lock karo
MFE_LOCK_FRACTION = 0.5


def _slip(price: float, side: str) -> float:
    f = 1 + SLIPPAGE_BPS / 10_000
    return price * f if side == "long" else price / f


@dataclass
class Trade:
    id: str
    timeframe: str
    side: str
    signal_time: int
    entry: float
    stop: float
    target: float
    quantity: float
    risk_cash: float
    opened_at: int = 0
    status: str = "OPEN"
    closed_at: int = 0
    exit: float = 0.0
    pnl: float = 0.0
    r_multiple: float = 0.0
    exit_reason: str = ""  # target | stop | time | trailing | partial-target ...
    setup: str = ""
    bars_held: int = 0
    highest_price: float = 0.0  # trailing stop, long
    lowest_price: float = 0.0  # trailing stop, short
    trailing_active: bool = False
    risk_dist: float = 0.0  # entry par fixed risk distance (R ka denominator)
    mfe_r: float = 0.0  # peak favorable excursion (R me)
    mae_r: float = 0.0  # peak adverse excursion (R me)
    be_active: bool = False  # Stage 1: breakeven lag gaya
    partial_taken: bool = False  # Stage 2: 50% partial ho gaya
    partial_pnl: float = 0.0  # partial se realized pnl
    mfe_lock_active: bool = False  # Stage 4: peak-lock lag gaya


@dataclass
class Engine:
    """Ek symbol ka journal. Har timeframe ka ek OPEN max, kul MAX_OPEN."""

    equity: float = INITIAL_EQUITY
    realized: float = 0.0
    pending: list = field(default_factory=list)  # (signal, timeframe)
    open_trades: list[Trade] = field(default_factory=list)
    closed: list[Trade] = field(default_factory=list)
    copy: list[dict] = field(default_factory=list)  # SEEKHNE WALI COPY
    _n: int = 0
    invalid_skipped: int = 0  # ulti geometry wale signal/entry skip hue

    def queue(self, signal, timeframe: str) -> None:
        """Signal aaya — agli candle ka intezar (entry abhi NAHI)."""
        if any(t.timeframe == timeframe and t.status == "OPEN" for t in self.open_trades):
            return  # is TF ka khula hai, naya nahi
        if len(self.open_trades) >= MAX_OPEN:
            return  # bheed ban, signal choro
        self.pending.append((signal, timeframe))

    def on_candle(self, timeframe: str, c: Candle, tf_ms: int) -> None:
        """Har band candle par: purano ka hisaab, phir pending ki entry."""
        for t in list(self.open_trades):
            if t.timeframe != timeframe:
                continue
            t.bars_held += 1

            # MFE/MAE tracking — R denominator FIXED (entry ka risk_dist)
            rd = t.risk_dist if t.risk_dist > 0 else abs(t.entry - t.stop)
            if t.side == "long":
                fav = (c.high - t.entry) / rd
                adv = (t.entry - c.low) / rd
            else:
                fav = (t.entry - c.low) / rd
                adv = (c.high - t.entry) / rd
            if fav > t.mfe_r:
                t.mfe_r = fav
            if adv > t.mae_r:
                t.mae_r = adv

            # Stage 1: BE @1.5R — stop ko breakeven (+fee/slip buffer) par lao
            if not t.be_active and fav >= BE_ACTIVATION_R:
                t.be_active = True
                buf = t.entry * (2 * FEE_RATE + 2 * SLIPPAGE_BPS / 10000)
                be_stop = t.entry + buf if t.side == "long" else t.entry - buf
                if t.side == "long":
                    if be_stop > t.stop:
                        t.stop = be_stop
                else:
                    if be_stop < t.stop:
                        t.stop = be_stop

            # Stage 2: 50% partial @2.5R — aadha qty market par band, runner rakho
            if not t.partial_taken and fav >= PARTIAL_ACTIVATION_R:
                t.partial_taken = True
                pq = t.quantity * PARTIAL_FRACTION
                px = _slip(c.close, "short" if t.side == "long" else "long")
                pgross = (px - t.entry) * pq if t.side == "long" else (t.entry - px) * pq
                pfee = (t.entry + px) * pq * FEE_RATE
                t.partial_pnl += pgross - pfee
                t.quantity -= pq

            # Gap rule: stop/target se paar khula to OPEN par bharo (stop price par nahi).
            # Stop gap = nuksan (open worse), target gap = fayda (open better, limit se behtar bharega).
            if t.side == "long":
                stop_fill = t.stop if c.open >= t.stop else c.open
                tgt_fill = t.target if c.open <= t.target else c.open
            else:
                stop_fill = t.stop if c.open <= t.stop else c.open
                tgt_fill = t.target if c.open >= t.target else c.open
            hit_stop = c.low <= t.stop if t.side == "long" else c.high >= t.stop
            hit_tgt = c.high >= t.target if t.side == "long" else c.low <= t.target
            if hit_stop and hit_tgt:
                self._close(t, stop_fill, c.time, "stop")  # stop-first (safe)
            elif hit_tgt:
                self._close(t, tgt_fill, c.time, "target")
            elif hit_stop:
                self._close(t, stop_fill, c.time, "stop")
            elif t.bars_held >= MAX_BARS:
                self._close(t, c.close, c.time, "time")

            # Stage 3+4: trailing/MFE-lock updates CLOSE par — agle candle se
            # effective (same-candle high se bana stop same-candle low ko
            # nahi maar sakta — intrabar sequencing rule).
            if t.status != "OPEN":
                continue
            # Stage 3: peak + giveback trail @2.5R
            if TRAILING_STOP_ENABLED and fav >= TRAILING_ACTIVATION_R:
                if not t.trailing_active:
                    t.trailing_active = True
                    if t.side == "long":
                        t.highest_price = c.high
                    else:
                        t.lowest_price = c.low
            if TRAILING_STOP_ENABLED and t.trailing_active:
                if t.side == "long":
                    if c.high > t.highest_price:
                        t.highest_price = c.high
                        new_stop = t.highest_price - (t.highest_price - t.entry) * TRAILING_GIVEBACK
                        if new_stop > t.stop:
                            t.stop = new_stop
                else:
                    if c.low < t.lowest_price:
                        t.lowest_price = c.low
                        new_stop = t.lowest_price + (t.entry - t.lowest_price) * TRAILING_GIVEBACK
                        if new_stop < t.stop:
                            t.stop = new_stop

            # Stage 4: MFE-lock @5R — stop = entry + peak ka 50% (ratchet only)
            if t.mfe_r >= MFE_LOCK_ACTIVATION_R:
                t.mfe_lock_active = True
            if t.mfe_lock_active:
                if t.side == "long":
                    lock = t.entry + MFE_LOCK_FRACTION * t.mfe_r * rd
                    if lock > t.stop:
                        t.stop = lock
                else:
                    lock = t.entry - MFE_LOCK_FRACTION * t.mfe_r * rd
                    if lock < t.stop:
                        t.stop = lock

        for signal, tf in [p for p in self.pending if p[1] == timeframe]:
            if any(t.timeframe == tf and t.status == "OPEN" for t in self.open_trades):
                self.pending.remove((signal, tf))
                continue  # is TF par pehle se khula — ek TF par ek

            # OTE entry: 45-88% retracement ka intezar, max 3 candles; phir market fallback
            c_open, c_high, c_low = c.open, c.high, c.low
            is_ote_entry = False
            if signal.side == "long":
                ote_low = signal.entry - (signal.entry - signal.stop) * 0.79
                ote_high = signal.entry - (signal.entry - signal.stop) * 0.62
                if c_low <= ote_high and c_high >= ote_low:
                    entry = min(c_high, max(ote_low, ote_high))
                    is_ote_entry = True
                    self.pending.remove((signal, tf))
                else:
                    waits = getattr(signal, "ote_wait_candles", 0) + 1
                    signal.ote_wait_candles = waits
                    if waits >= 3:
                        entry = c.close
                        self.pending.remove((signal, tf))
                    else:
                        continue  # retracement ka intezar
            else:
                ote_low = signal.entry + (signal.stop - signal.entry) * 0.38
                ote_high = signal.entry + (signal.stop - signal.entry) * 0.62
                if c_low <= ote_high and c_high >= ote_low:
                    entry = max(c_low, min(ote_low, ote_high))
                    is_ote_entry = True
                    self.pending.remove((signal, tf))
                else:
                    waits = getattr(signal, "ote_wait_candles", 0) + 1
                    signal.ote_wait_candles = waits
                    if waits >= 3:
                        entry = c.close
                        self.pending.remove((signal, tf))
                    else:
                        continue  # retracement ka intezar

            risk_cash = self.equity * RISK_PCT
            if getattr(signal, "counter_trend", False):
                risk_cash *= 0.5  # counter-trend: aadha risk
            # signal ke entry se stop/target ka distance nikaalo
            if signal.side == "long":
                stop_dist = signal.entry - signal.stop
                target_dist = signal.target - signal.entry
            else:
                stop_dist = signal.stop - signal.entry
                target_dist = signal.entry - signal.target
            if stop_dist <= 0 or target_dist <= 0:
                continue  # ganda geometry — skip
            # qty full stop_dist pe calculate karo (signal.entry → signal.stop)
            qty = risk_cash / stop_dist
            # OTE entry: stop ko signal.stop par lock, qty aadha, target distance same
            if is_ote_entry:
                actual_stop = signal.stop
                actual_target = entry + target_dist if signal.side == "long" else entry - target_dist
                qty *= 0.5
                dist = stop_dist  # risk_cash normalization ke liye
            else:
                actual_stop = entry - stop_dist if signal.side == "long" else entry + stop_dist
                actual_target = entry + target_dist if signal.side == "long" else entry - target_dist
                dist = stop_dist
            if dist <= 0:
                continue
            # Geometry guard: stop/target sahi side par hone chahiye, warna skip + gino
            if signal.side == "long":
                if not (actual_stop < entry < actual_target):
                    self.invalid_skipped += 1
                    continue
            else:
                if not (actual_target < entry < actual_stop):
                    self.invalid_skipped += 1
                    continue
            self._n += 1
            ct = getattr(signal, "counter_trend", False)
            self.open_trades.append(
                Trade(
                    id=f"T{self._n}", timeframe=tf, side=signal.side, signal_time=c.time,
                    entry=entry, stop=actual_stop, target=actual_target,
                    quantity=qty, risk_cash=risk_cash, opened_at=c.time,
                    setup=("CT-" if ct else "") + signal.event,
                    risk_dist=abs(entry - actual_stop),
                )
            )
            # Telegram entry notification
            if TELEGRAM_ENABLED and _notifier:
                try:
                    rr = abs(actual_target - entry) / dist if dist > 0 else 0.0
                    notify_entry_sync(
                        trade_id=f"T{self._n}", symbol="SYMBOL", tf=tf, side=signal.side,
                        entry=entry, stop=actual_stop, target=actual_target, qty=qty,
                        risk_cash=risk_cash, rr=rr, setup=("CT-" if ct else "") + signal.event
                    )
                except Exception as e:
                    print(f"Telegram entry notify error: {e}")

    def _close(self, t: Trade, raw_exit: float, when: int, reason: str) -> None:
        t.exit = _slip(raw_exit, "short" if t.side == "long" else "long")
        gross = (t.exit - t.entry) * t.quantity if t.side == "long" else (t.entry - t.exit) * t.quantity
        fee = (t.entry + t.exit) * t.quantity * FEE_RATE
        t.pnl = t.partial_pnl + gross - fee  # partial + runner
        t.r_multiple = t.pnl / t.risk_cash if t.risk_cash else 0.0
        t.status, t.closed_at, t.exit_reason = "CLOSED", when, reason
        self.open_trades.remove(t)
        self.closed.append(t)
        self.realized += t.pnl
        self.equity = INITIAL_EQUITY + self.realized
        self.copy.append({  # SEEKHNE WALI COPY — har band trade
            "id": t.id, "timeframe": t.timeframe, "setup": t.setup,
            "result": "WIN" if t.pnl > 0 else ("LOSS" if t.pnl < 0 else "FLAT"),
            "r": round(t.r_multiple, 2), "reason": reason,
            "mfe_r": round(t.mfe_r, 2), "mae_r": round(t.mae_r, 2),
            "partial_r": round(t.partial_pnl / t.risk_cash, 2) if t.risk_cash else 0.0,
        })
        # Telegram exit notification
        if TELEGRAM_ENABLED and _notifier:
            try:
                notify_exit_sync(
                    trade_id=t.id, symbol="SYMBOL", tf=t.timeframe, side=t.side,
                    entry=t.entry, exit_price=t.exit, pnl=t.pnl,
                    r_multiple=t.r_multiple, exit_reason=reason, bars_held=t.bars_held,
                    mfe_r=t.mfe_r, mae_r=t.mae_r, partial_r=round(t.partial_pnl / t.risk_cash, 2) if t.risk_cash else 0.0
                )
            except Exception as e:
                print(f"Telegram exit notify error: {e}")

    def summary(self) -> dict:
        wins = sum(1 for t in self.closed if t.pnl > 0)
        rs = [t.r_multiple for t in self.closed]
        mfes = [t.mfe_r for t in self.closed]
        maes = [t.mae_r for t in self.closed]
        avg_mfe = sum(mfes) / len(mfes) if mfes else 0.0
        avg_mae = sum(maes) / len(maes) if maes else 0.0
        capture = (sum(rs) / sum(mfes)) if mfes and sum(mfes) > 0 else 0.0
        return {
            "equity": round(self.equity, 2),
            "realized": round(self.realized, 2),
            "open": len(self.open_trades),
            "closed": len(self.closed),
            "wins": wins,
            "win_rate": round(wins / len(self.closed) * 100, 1) if self.closed else 0.0,
            "avg_r": round(sum(rs) / len(rs), 2) if rs else 0.0,
            "avg_mfe": round(avg_mfe, 2),
            "avg_mae": round(avg_mae, 2),
            "capture_rate": round(capture, 2),
            "invalid_skipped": self.invalid_skipped,
        }
