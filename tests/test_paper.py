"""Paper engine tests — entry timing, exits, copy (offline, nakli data)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.signal import Signal
from market.binance import Candle
from paper.journal import Engine

TF = 5 * 60 * 1000


def sig(side="long", entry=100.0, stop=99.0, target=102.5) -> Signal:
    return Signal(side=side, entry=entry, stop=stop, target=target, rr=2.5,
                 reason="t", event="fvg_retrace", index=0, confidence=0.7)


def candle(t: int, o: float, h: float, low: float, cl: float) -> Candle:
    return Candle(time=t, open=o, high=h, low=low, close=cl, volume=5.0)


def test_entry_next_candle_not_same():
    e = Engine()
    e.queue(sig(), "5m")
    e.on_candle("5m", candle(1000, 100, 101, 99.5, 100.5), TF)  # entry wali
    assert len(e.open_trades) == 1
    assert e.open_trades[0].opened_at == 1000


def test_target_win_and_copy():
    e = Engine()
    e.queue(sig(), "5m")
    e.on_candle("5m", candle(1000, 100, 101, 99.5, 100.5), TF)
    e.on_candle("5m", candle(2000, 100.5, 103.0, 100.0, 102.8), TF)  # target laga
    assert e.open_trades == []
    assert len(e.closed) == 1
    assert e.closed[0].exit_reason == "target"
    assert e.copy[0]["result"] == "WIN"
    assert e.summary()["wins"] == 1


def test_stop_first_on_ambiguous():
    e = Engine()
    e.queue(sig(), "5m")
    e.on_candle("5m", candle(1000, 100, 101, 99.5, 100.5), TF)
    e.on_candle("5m", candle(2000, 100.5, 103.0, 98.0, 99.0), TF)  # dono lage
    assert e.closed[0].exit_reason == "stop"  # safe side


def test_one_open_per_timeframe():
    e = Engine()
    e.queue(sig(), "5m")
    e.queue(sig(), "5m")
    e.on_candle("5m", candle(1000, 100, 101, 99.5, 100.5), TF)
    assert len(e.open_trades) == 1  # doosra gira diya


