"""ICT primitives — Five-main ict-primitives.ts ka Python copy.

Same math: true range, ATR(14), confirmed swings (2/2), FVG detect.
"""
from dataclasses import dataclass

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market.binance import Candle  # noqa: E402


@dataclass
class Swing:
    index: int
    price: float
    side: str  # "high" | "low"


def true_range(candles: list[Candle], index: int) -> float:
    cur = candles[index]
    if index == 0:
        return cur.high - cur.low
    prev = candles[index - 1]
    return max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close))


def atr(candles: list[Candle], end: int, period: int = 14) -> float:
    start = max(0, end - period + 1)
    vals = [true_range(candles, i) for i in range(start, end + 1) if true_range(candles, i) > 0]
    return sum(vals) / len(vals) if vals else 0.0


def _is_swing_high(candles: list[Candle], i: int, left: int = 2, right: int = 2, end: int = 0) -> bool:
    if i < left or i + right > end:
        return False
    p = candles[i].high
    return all(j == i or candles[j].high < p for j in range(i - left, i + right + 1))


def _is_swing_low(candles: list[Candle], i: int, left: int = 2, right: int = 2, end: int = 0) -> bool:
    if i < left or i + right > end:
        return False
    p = candles[i].low
    return all(j == i or candles[j].low > p for j in range(i - left, i + right + 1))


def confirmed_swings(candles: list[Candle], end: int, left: int = 2, right: int = 2, lookback: int = 60) -> list[Swing]:
    last = end - right
    first = max(left, last - lookback)
    out: list[Swing] = []
    for i in range(first, last + 1):
        if _is_swing_high(candles, i, left, right, end):
            out.append(Swing(index=i, price=candles[i].high, side="high"))
        if _is_swing_low(candles, i, left, right, end):
            out.append(Swing(index=i, price=candles[i].low, side="low"))
    return sorted(out, key=lambda s: s.index)


def detect_fvg(candles: list[Candle], index: int) -> str | None:
    """Teen candle ka gap: bullish / bearish / None (same as TS)."""
    if index < 2:
        return None
    first, mid, third = candles[index - 2], candles[index - 1], candles[index]
    if third.low > first.high and mid.close >= mid.open:
        return "bullish"
    if third.high < first.low and mid.close <= mid.open:
        return "bearish"
    return None
