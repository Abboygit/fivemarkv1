"""Paper trading journal — nakli paise, asli hisaab. LIVE ORDER KA ZIKR BAN HAI.

Design: Paper Trading design.md ($10k, 1% risk, agli-candle entry, stop-first).
Seekhne wali copy: har band trade yahin likha jayega (Signal Engine 6B).
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market.binance import Candle  # noqa: E402

INITIAL_EQUITY = 10_000.0
RISK_PCT = 0.01
FEE_RATE = 0.0004
SLIPPAGE_BPS = 1.0
MAX_BARS = 60
MAX_OPEN = 5
MAX_NOTIONAL_X = 2.0  # position itni badi nahi ke fee hi kha jaye (backtest #1 ka seekh)


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
    exit_reason: str = ""  # target | stop | time
    setup: str = ""
    bars_held: int = 0


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
            hit_stop = c.low <= t.stop if t.side == "long" else c.high >= t.stop
            hit_tgt = c.high >= t.target if t.side == "long" else c.low <= t.target
            if hit_stop and hit_tgt:
                self._close(t, t.stop, c.time, "stop")  # stop-first (safe)
            elif hit_tgt:
                self._close(t, t.target, c.time, "target")
            elif hit_stop:
                self._close(t, t.stop, c.time, "stop")
            elif t.bars_held >= MAX_BARS:
                self._close(t, c.close, c.time, "time")
        for signal, tf in [p for p in self.pending if p[1] == timeframe]:
            self.pending.remove((signal, tf))
            if any(t.timeframe == tf and t.status == "OPEN" for t in self.open_trades):
                continue  # is candle me pehle hi khul gaya / pehle se khula — ek TF par ek
            entry = _slip(c.open, signal.side)
            risk_cash = self.equity * RISK_PCT
            if getattr(signal, "counter_trend", False):
                risk_cash *= 0.5  # counter-trend: aadha risk
            # signal ke entry se stop/target ka distance nikaalo, actual entry pe apply karo
            if signal.side == "long":
                stop_dist = signal.entry - signal.stop
                target_dist = signal.target - signal.entry
            else:
                stop_dist = signal.stop - signal.entry
                target_dist = signal.entry - signal.target
            if stop_dist <= 0 or target_dist <= 0:
                continue  # ganda geometry — skip
            dist = stop_dist  # risk distance from actual entry
            if dist <= 0:
                continue
            qty = risk_cash / dist
            if qty * entry > MAX_NOTIONAL_X * self.equity:
                qty = (MAX_NOTIONAL_X * self.equity) / entry
                risk_cash = qty * dist
            actual_stop = entry - stop_dist if signal.side == "long" else entry + stop_dist
            actual_target = entry + target_dist if signal.side == "long" else entry - target_dist
            self._n += 1
            ct = getattr(signal, "counter_trend", False)
            self.open_trades.append(
                Trade(
                    id=f"T{self._n}", timeframe=tf, side=signal.side, signal_time=c.time,
                    entry=entry, stop=actual_stop, target=actual_target,
                    quantity=qty, risk_cash=risk_cash, opened_at=c.time,
                    setup=("CT-" if ct else "") + signal.event,
                )
            )

    def _close(self, t: Trade, raw_exit: float, when: int, reason: str) -> None:
        t.exit = _slip(raw_exit, "short" if t.side == "long" else "long")
        gross = (t.exit - t.entry) * t.quantity if t.side == "long" else (t.entry - t.exit) * t.quantity
        fee = (t.entry + t.exit) * t.quantity * FEE_RATE
        t.pnl = gross - fee
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
        })

    def summary(self) -> dict:
        wins = sum(1 for t in self.closed if t.pnl > 0)
        rs = [t.r_multiple for t in self.closed]
        return {
            "equity": round(self.equity, 2),
            "realized": round(self.realized, 2),
            "open": len(self.open_trades),
            "closed": len(self.closed),
            "wins": wins,
            "win_rate": round(wins / len(self.closed) * 100, 1) if self.closed else 0.0,
            "avg_r": round(sum(rs) / len(rs), 2) if rs else 0.0,
        }
