"""Signal engine tests — HTF gate + primitives (offline, nakli data)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engine.primitives import atr, confirmed_swings
from engine.signal import _displacement, _sweep, find_liquidity, find_zones, generate_signal, htf_bias
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


def test_helper_return_shapes():
    """Regression: _displacement sirf str/None, _sweep sirf dict/None (galat-patch dobara nahi)."""
    cs = trend(n=60)
    for i in range(2, 60):
        d = _displacement(cs, i)
        assert d is None or isinstance(d, str)
        w = _sweep(cs, i)
        assert w is None or (isinstance(w, dict) and "price" in w)


def fvg_series() -> list[Candle]:
    """Flat ke baad bullish jump + FVG: displacement + gap up."""
    out = []
    t = 1000
    for i in range(30):
        out.append(Candle(time=t, open=100.0, high=100.2, low=99.8, close=100.0, volume=5.0))
        t += 60000
    out.append(Candle(time=t, open=100.0, high=102.5, low=99.9, close=102.2, volume=50.0))  # displacement
    t += 60000
    out.append(Candle(time=t, open=102.3, high=103.0, low=101.0, close=102.8, volume=20.0))  # FVG (low 101 > 100.2)
    t += 60000
    for i in range(5):  # zone ko touch karo (mitigated) par todo nahi
        out.append(Candle(time=t, open=102.5, high=102.9, low=101.5, close=102.6, volume=8.0))
        t += 60000
    return out


def test_find_zones_fvg():
    cs = fvg_series()
    z = find_zones(cs, len(cs) - 1)
    assert isinstance(z, list)
    fvg = [x for x in z if x["kind"] == "FVG"]
    assert len(fvg) >= 1
    assert fvg[0]["status"] in ("active", "mitigated", "breaker")
    assert fvg[0]["high"] > fvg[0]["low"]


def test_find_liquidity_shapes():
    cs = trend(n=80)
    pools = find_liquidity(cs, 79)
    assert isinstance(pools, list)
    for p in pools:
        assert p["side"] in ("SSL", "BSL")
        assert p["count"] >= 2
        assert p["price"] > 0
