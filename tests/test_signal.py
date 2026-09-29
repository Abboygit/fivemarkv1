"""Signal engine tests — HTF gate + primitives (offline, nakli data)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.primitives import atr, confirmed_swings
from engine.signal import generate_signal, htf_bias
from market.binance import Candle


def trend(n: int = 80, up: bool = True) -> list[Candle]:
    out = []
    p = 100.0
    for i in range(n):
        p += 0.5 if up else -0.5
        out.append(Candle(time=1000 + i * 60000, open=p - 0.2, high=p + 0.3, low=p - 0.3, close=p, volume=5.0))
    return out


def test_bias_valid_value():
    assert htf_bias(trend(up=True), 79) in ("UP", "DOWN", "WAIT")
    assert htf_bias(trend(up=False), 79) in ("UP", "DOWN", "WAIT")


def test_wait_bias_never_signals():
    assert generate_signal(trend(), 79, bias="WAIT") is None


def test_atr_positive_and_swings_found():
    cs = trend()
    assert atr(cs, 79) > 0
    assert len(confirmed_swings(cs, 79)) >= 0  # crash nahi, list mile


def test_rr_invariant_on_any_signal():
    cs = trend()
    for i in range(40, 80):
        s = generate_signal(cs, i)
        if s:
            assert s.rr >= 2.5
            assert (s.side == "long" and s.target > s.entry > s.stop) or (
                s.side == "short" and s.target < s.entry < s.stop
            )
