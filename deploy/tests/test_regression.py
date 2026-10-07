"""Regression tests — backtest honesty locks (dobara tootne nahi chahiye).

1. no-lookahead: signal(i) full data par == truncated data [:i+1] par
2. next-bar fill: entry hamesha queue-ke-baadd wali candle se, signal close se kabhi nahi
3. gap-through-stop: stop se paar khula to OPEN par bharo, stop price par nahi
4. stop-wins-tie: ek candle me stop+target dono lage to reason "stop"
5. mfe-mae: har band trade par mfe_r/mae_r tracked + copy/summary me reported
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.signal import Signal, generate_signal
from market.binance import Candle
from paper.journal import Engine

TF = 5 * 60 * 1000


def trend(n: int = 80, up: bool = True) -> list[Candle]:
    out = []
    p = 100.0
    for i in range(n):
        p += 0.5 if up else -0.5
        out.append(Candle(time=1000 + i * 60000, open=p - 0.2, high=p + 0.3,
                          low=p - 0.3, close=p, volume=5.0))
    return out


def sig(side="long", entry=100.0, stop=99.0, target=102.5) -> Signal:
    return Signal(side=side, entry=entry, stop=stop, target=target, rr=2.5,
                 reason="t", event="fvg_retrace", index=0, confidence=0.7)


def candle(t: int, o: float, h: float, low: float, cl: float) -> Candle:
    return Candle(time=t, open=o, high=h, low=low, close=cl, volume=5.0)


def test_no_lookahead_full_vs_truncated():
    """Signal(i) ko candles[i+1:] kabhi nahi dikhne chahiye (FVG ev+1 guard)."""
    for data in (trend(80, True), trend(80, False)):
        for bias in ("BOTH", "UP", "DOWN"):
            for i in range(40, 80):
                a = generate_signal(data, i, bias=bias)
                b = generate_signal(data[: i + 1], i, bias=bias)
                assert a == b, f"lookahead leak at i={i} bias={bias}: {a} != {b}"


def test_next_bar_fill_never_signal_close():
    """Entry queue-ke-baadd wali candle se — 2 wait candles par koi entry nahi,
    teesri par fallback entry usi candle ke close par."""
    e = Engine()
    e.queue(sig(), "5m")
    e.on_candle("5m", candle(1000, 100, 101, 99.5, 100.5), TF)  # dip nahi
    e.on_candle("5m", candle(2000, 100, 101, 99.5, 100.5), TF)  # dip nahi
    assert e.open_trades == []
    e.on_candle("5m", candle(3000, 100, 101, 99.5, 100.5), TF)  # fallback
    assert len(e.open_trades) == 1
    t = e.open_trades[0]
    assert t.entry == 100.5  # teesri candle ka close
    assert t.opened_at == 3000


def test_gap_through_stop_fills_at_open():
    """Long stop 99.0, candle 98.5 par khuli (gap through) → exit ~98.49 (open-slipped),
    stop price 99.0 par NAHI."""
    e = Engine()
    e.queue(sig(), "5m")
    e.on_candle("5m", candle(1000, 100, 101, 99.0, 100.5), TF)  # OTE entry 99.38, stop 99.0
    assert len(e.open_trades) == 1
    e.on_candle("5m", candle(2000, 98.5, 98.8, 97.0, 97.5), TF)  # gap down through stop
    assert len(e.closed) == 1
    t = e.closed[0]
    assert t.exit_reason == "stop"
    assert t.exit < 99.0  # stop price par fill nahi hua
    assert abs(t.exit - 98.5 / 1.0001) < 1e-6  # open, slippage ke saath


def test_stop_wins_tie_when_both_hit():
    """Ek hi candle me stop (98) + target (101.88) dono lage → reason 'stop' (safe side)."""
    e = Engine()
    e.queue(sig(), "5m")
    e.on_candle("5m", candle(1000, 100, 101, 99.0, 100.5), TF)
    e.on_candle("5m", candle(2000, 100.5, 103.0, 98.0, 99.0), TF)  # dono lage
    assert len(e.closed) == 1
    assert e.closed[0].exit_reason == "stop"


def test_mfe_mae_tracked_and_reported():
    """Har band trade par mfe_r/mae_r; copy + summary me avg_mfe/avg_mae/capture_rate."""
    e = Engine()
    e.queue(sig(), "5m")
    e.on_candle("5m", candle(1000, 100, 101, 99.0, 100.5), TF)  # entry 99.38, risk_dist 0.38
    e.on_candle("5m", candle(2000, 100.5, 103.0, 100.0, 102.8), TF)  # target hit
    assert len(e.closed) == 1
    c = e.closed[0]
    assert c.mfe_r > 0
    assert c.mae_r >= 0
    assert abs(c.mfe_r - (103.0 - 99.38) / 0.38) < 0.05  # high 103 se peak
    assert "mfe_r" in e.copy[0] and "mae_r" in e.copy[0]
    s = e.summary()
    assert "avg_mfe" in s and "avg_mae" in s and "capture_rate" in s
    assert s["avg_mfe"] > 0
