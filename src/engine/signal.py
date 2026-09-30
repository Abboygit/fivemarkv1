"""Signal Engine — Five-main ict-v2.ts ka Python copy + HTF→LTF gate (hamara modification).

Flow: HTF rukh (UP/DOWN/WAIT) → LTF entry sirf rukh wali side me.
Steps: sweep + displacement + FVG/OB + retrace + premium/discount veto + stop/target + RR>=2.5.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market.binance import Candle  # noqa: E402
from engine.primitives import atr, confirmed_swings, detect_fvg  # noqa: E402

DISP_ATR = 1.25
DISP_RANGE_ATR = 1.6
RISK_REWARD = 2.5
PD_BUFFER = 0.08
LOOKBACK = 18


@dataclass
class Signal:
    side: str  # "long" | "short"
    entry: float
    stop: float
    target: float
    rr: float
    reason: str
    event: str  # "fvg_retrace" | "ob_retrace"
    index: int
    confidence: float
    zone_kind: str = ""  # "FVG" | "OB" (chart box ke liye)
    zone_high: float = 0.0
    zone_low: float = 0.0
    sweep_price: float = 0.0  # sweep point (chart dot ke liye)
    event_index: int = 0  # displacement wali candle (chart marker ke liye)


def _overlaps(c: Candle, low: float, high: float) -> bool:
    return c.low <= high and c.high >= low


def _displacement(candles: list[Candle], i: int) -> str | None:
    c = candles[i]
    a = atr(candles, i - 1) if i > 0 else 0.0
    if a <= 0:
        return None
    body, rng = abs(c.close - c.open), c.high - c.low
    if body < a * DISP_ATR or rng < a * DISP_RANGE_ATR:
        return None
    if c.close > c.open:
        return "bullish"
    if c.close < c.open:
        return {"direction": "bearish", "price": highs[-1].price}
    return None


def _sweep(candles: list[Candle], i: int) -> str | None:
    swings = confirmed_swings(candles, i)
    c, prev = candles[i], candles[i - 1] if i > 0 else None
    lows = [s for s in swings if s.side == "low" and s.index < i]
    highs = [s for s in swings if s.side == "high" and s.index < i]
    if lows and c.low < lows[-1].price and c.close > lows[-1].price and (prev is None or prev.low >= lows[-1].price):
        return {"direction": "bullish", "price": lows[-1].price}
    if highs and c.high > highs[-1].price and c.close < highs[-1].price and (prev is None or prev.high <= highs[-1].price):
        return "bearish"
    return None


def _mss_or_bos(candles: list[Candle], i: int, direction: str) -> bool:
    swings = confirmed_swings(candles, i)
    want = "high" if direction == "bullish" else "low"
    cands = [s for s in swings if s.side == want and s.index < i]
    if not cands:
        return False
    t = cands[-1]
    cur, prev = candles[i], candles[i - 1] if i > 0 else None
    if direction == "bullish":
        return cur.close > t.price and (prev is None or prev.close <= t.price)
    return cur.close < t.price and (prev is None or prev.close >= t.price)


def _fvg_zone(candles: list[Candle], disp_i: int, direction: str) -> dict | None:
    fvg_i = disp_i + 1
    if fvg_i >= len(candles) or detect_fvg(candles, fvg_i) != direction:
        return None
    first, third = candles[disp_i - 1], candles[fvg_i]
    if direction == "bullish":
        return {"kind": "FVG", "high": third.low, "low": first.high, "index": fvg_i}
    return {"kind": "FVG", "high": first.low, "low": third.high, "index": fvg_i}


def _ob_zone(candles: list[Candle], index: int, direction: str, lookback: int = 10) -> dict | None:
    for j in range(index - 1, max(-1, index - lookback) - 1, -1):
        c = candles[j]
        after = candles[j + 1 : index + 1]
        if not after:
            continue
        hi, lo = max(x.high for x in after), min(x.low for x in after)
        if direction == "bullish" and c.close < c.open and hi > c.high and candles[index].close > c.high:
            return {"kind": "OB", "high": c.open, "low": c.low, "index": j}
        if direction == "bearish" and c.close > c.open and lo < c.low and candles[index].close < c.low:
            return {"kind": "OB", "high": c.high, "low": c.open, "index": j}
    return None


def _premium_discount(price: float, hi: float, lo: float) -> str:
    n = (price - lo) / (hi - lo) if hi > lo else 0.5
    if n > 0.5 + PD_BUFFER:
        return "premium"
    if n < 0.5 - PD_BUFFER:
        return "discount"
    return "equilibrium"


def htf_bias(candles: list[Candle], index: int) -> str:
    """HTF rukh: UP / DOWN / WAIT. Structure + premium/discount se."""
    start = max(0, index - 59)
    window = candles[start : index + 1]
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    pd = _premium_discount(candles[index].close, hi, lo)
    swings = confirmed_swings(candles, index)
    highs = [s.price for s in swings if s.side == "high"]
    lows = [s.price for s in swings if s.side == "low"]
    up = len(highs) >= 2 and len(lows) >= 2 and highs[-1] > highs[-2] and lows[-1] > lows[-2]
    dn = len(highs) >= 2 and len(lows) >= 2 and highs[-1] < highs[-2] and lows[-1] < lows[-2]
    if up and pd != "premium":
        return "UP"
    if dn and pd != "discount":
        return "DOWN"
    # NARM GATE (backtest #1 ka seekh): structure saaf na ho to aakhri 20 close ka rujhan dekho
    tail = candles[max(0, index - 20) : index + 1]
    if len(tail) >= 10:
        if tail[-1].close > tail[0].close * 1.002 and pd != "premium":
            return "UP"
        if tail[-1].close < tail[0].close * 0.998 and pd != "discount":
            return "DOWN"
    return "WAIT"


def generate_signal(candles: list[Candle], index: int, bias: str = "BOTH") -> Signal | None:
    """LTF signal. bias=UP/DOWN/WAIT (HTF gate) ya BOTH (gate bandh, test ke liye)."""
    if index < 30 or index >= len(candles):
        return None
    cur = candles[index]
    for ev in range(index, max(index - LOOKBACK, 0) - 1, -1):
        direction = _displacement(candles, ev)
        if not direction:
            continue
        sweep = _sweep(candles, ev)
        struct = _mss_or_bos(candles, ev, direction)
        if not sweep and not struct:
            continue
        zone = _fvg_zone(candles, ev, direction) or _ob_zone(candles, index, direction)
        if not zone or zone["index"] >= index:
            continue
        if not _overlaps(cur, zone["low"], zone["high"]):
            continue
        side = "long" if direction == "bullish" else "short"
        if bias == "UP" and side != "long":
            continue  # HTF gate: bada UP, chota sell ban
        if bias == "DOWN" and side != "short":
            continue
        if bias == "WAIT":
            return None
        start = max(0, index - 59)
        hi = max(c.high for c in candles[start : index + 1])
        lo = min(c.low for c in candles[start : index + 1])
        pd = _premium_discount(cur.close, hi, lo)
        if side == "long" and pd == "premium":
            continue
        if side == "short" and pd == "discount":
            continue
        swings = confirmed_swings(candles, index)
        entry = cur.close
        if side == "long":
            stops = sorted([s.price for s in swings if s.side == "low" and s.price < entry], key=lambda p: entry - p)
            targets = sorted([s.price for s in swings if s.side == "high" and s.price > entry])
        else:
            stops = sorted([s.price for s in swings if s.side == "high" and s.price > entry], key=lambda p: p - entry)
            targets = sorted([s.price for s in swings if s.side == "low" and s.price < entry])
        if not stops or not targets:
            continue
        stop, target = stops[0], targets[0]
        dist = abs(entry - stop)
        if not (entry * 0.0005 <= dist <= entry * 0.03):
            continue
        if abs(target - entry) < dist * RISK_REWARD:
            continue
        conf = 0.2 * bool(sweep) + 0.25 * bool(struct) + 0.25 + 0.2 + 0.1
        reason = f"{'sweep+' if sweep else ''}{'mss/bos+' if struct else ''}displacement+{zone['kind']}+{pd}"
        return Signal(
            side=side, entry=entry, stop=stop, target=target,
            rr=abs(target - entry) / dist, reason=reason,
            event=f"{zone['kind'].lower()}_retrace", index=index, confidence=round(conf, 2),
            zone_kind=zone["kind"], zone_high=zone["high"], zone_low=zone["low"],
            sweep_price=sweep["price"] if sweep else 0.0, event_index=ev,
        )
    return None


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from market.binance import fetch_klines

    htf = fetch_klines("BTCUSDT", "1h", 120)[:-1]  # band only (aakhri chalti bahar)
    ltf = fetch_klines("BTCUSDT", "5m", 120)[:-1]
    bias = htf_bias(htf, len(htf) - 1)
    print(f"HTF(1h) rukh: {bias}")
    sig = generate_signal(ltf, len(ltf) - 1, bias=bias)
    print(f"LTF(5m) signal: {sig}")
